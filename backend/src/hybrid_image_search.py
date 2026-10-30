"""Candidate selection only. Qdrant retains sole responsibility for ranking.

Margins are retrieval heuristics, not calibrated confidence probabilities.
No model, ingestion labels, vector score thresholds or weighted ranking here.
"""
import math
from .zero_shot_classifier import ATTRIBUTE_LABELS

CANDIDATE_POOL_MULTIPLIER = 4
MAX_HARD_FILTERS = 2
MIN_ATTRIBUTE_MARGIN = 0.015
# Style is subjective; require a wider separation than basic visual attributes.
MIN_STYLE_MARGIN = 0.04


def reliable_image_attributes(attributes, mandatory=None):
    """Existing v2 reliability/order rules, shared with strict image matching."""
    mandatory = mandatory or {}
    eligible = []
    for key, labels in ATTRIBUTE_LABELS.items():
        if key in mandatory:
            continue
        prediction = attributes.get(key, {})
        margin = prediction.get('margin', 0)
        score = prediction.get('score', 0)
        threshold = MIN_STYLE_MARGIN if key == 'style' else MIN_ATTRIBUTE_MARGIN
        if (prediction.get('label') in labels and prediction.get('runner_up') in labels
                and math.isfinite(margin) and math.isfinite(score)
                and margin >= threshold and score > 0):
            eligible.append((key, prediction))
    eligible.sort(key=lambda item: item[1]['margin'], reverse=True)
    return eligible


def image_strategy(mode, filters, mandatory=None):
    """Describe the actual effective constraints, never model reasoning."""
    mandatory = mandatory or {}
    if mode == 'exact':
        return 'strict_attributes' if filters else 'attributes_required'
    if mode == 'auto' and any(key not in mandatory for key in filters):
        return 'attribute_guided'
    return 'explicit_text_filtered_similarity' if mandatory else 'pure_image_similarity'


def retrieve_hybrid(vector, attributes, limit, count_candidates, query_points, build_filter, mandatory=None):
    """Optional image guesses may relax; mandatory text constraints never do.

    Empty mandatory keeps the original v2 policy. Callbacks use the existing
    collection; Qdrant retains ordering and diagnostics remain server-side.
    """
    target = CANDIDATE_POOL_MULTIPLIER * limit
    mandatory = dict(mandatory or {})
    selected = {}
    trace = {'target_candidates': target, 'ordered_margins': [], 'attempts': [],
             'relaxations': [], 'candidate_availability': None}
    eligible = reliable_image_attributes(attributes, mandatory)
    trace['ordered_margins'] = [
        {'attribute': key, 'margin': prediction['margin']} for key, prediction in
        sorted(attributes.items(), key=lambda item: item[1]['margin'], reverse=True)]
    for key, prediction in eligible:
        if len(selected) >= MAX_HARD_FILTERS:
            break
        # Same Boolean normalization as ingestion; other labels stay literal.
        value = prediction['label'] == 'with visible buttons' if key == 'buttons' else prediction['label']
        trial = {**mandatory, **selected, key: value}
        try:
            count = count_candidates(build_filter(trial))
        except Exception as exc:
            # Count unavailable: discard image guesses, retaining mandatory text.
            trace['attempts'].append({'filters': trial, 'decision': 'count_unavailable',
                                      'error_type': type(exc).__name__})
            selected.clear()
            trace['candidate_availability'] = None
            break
        accepted = count >= target
        trace['attempts'].append({'filters': trial, 'candidate_count': count,
                                  'decision': 'accepted' if accepted else 'pool_too_small'})
        if not accepted:
            break  # Do not replace a stronger constraint with weaker guesses.
        selected[key] = value
        trace['candidate_availability'] = count

    # Counts may race with collection changes. Relax the weakest accepted filter.
    while True:
        try:
            points = query_points(vector, build_filter({**mandatory, **selected}), limit)
        except Exception as exc:
            if not selected:
                raise  # A mandatory-only/baseline outage reaches API handling.
            points = []
            reason = 'filtered_query_unavailable'
            error_type = type(exc).__name__
        else:
            reason = 'too_few_results'
            error_type = None
        if len(points) >= limit or not selected:
            break
        weakest = next(reversed(selected))
        trace['relaxations'].append({'attribute': weakest, 'reason': reason,
                                     'result_count': len(points), 'error_type': error_type})
        del selected[weakest]
        trace['candidate_availability'] = None
    if trace['candidate_availability'] is None:
        try:
            trace['candidate_availability'] = count_candidates(build_filter({**mandatory, **selected}))
        except Exception:
            pass
    trace['final_filters'] = {**mandatory, **selected}
    trace['final_result_count'] = len(points)
    analysis = {
        'attributes': {key: {**value, 'used_for_filter': key in selected}
                       for key, value in attributes.items()},
        'filters_used': {**mandatory, **selected},
        'strategy': 'image_with_attribute_override' if mandatory else ('attribute_guided_visual' if selected else 'pure_visual'),
        'candidate_count': trace['candidate_availability'],
    }
    return points, analysis, trace
