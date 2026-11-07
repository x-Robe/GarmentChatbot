"""Recompute human P@5, coverage and paired ablation; standard library only.

Run: python evaluation/calculate_metrics.py
Blank labels are pending, never zero. A complete label requires reviewer identity.
For a successful zero-result query, fill queries.csv reviewed_by to acknowledge
review; it can then receive P@5=0 without manufacturing annotation rows.
"""
import argparse
import csv
from pathlib import Path


def read_csv(path):
    with path.open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def key(row):
    return tuple(row[name] for name in ('query_id', 'variant', 'rank', 'product_id'))


def calculate(directory):
    queries = {r['query_id']: r for r in read_csv(directory / 'queries.csv')}
    runs = read_csv(directory / 'runs.csv')
    results = read_csv(directory / 'results.csv')
    annotations = read_csv(directory / 'annotations.csv')
    labels = {}
    for row in annotations:
        k = key(row)
        if k in labels:
            raise ValueError('Duplicate annotation key')
        label = row['relevance'].strip()
        if label not in ('', '0', '1'):
            raise ValueError('Relevance must be blank, 0 or 1')
        labels[k] = row
    result_keys = [key(r) for r in results]
    if len(result_keys) != len(set(result_keys)) or set(result_keys) != set(labels):
        raise ValueError('Annotation rows must match current retrieval results exactly')
    run_keys = [(r['query_id'], r['variant']) for r in runs]
    if len(run_keys) != len(set(run_keys)):
        raise ValueError('Duplicate run')
    if any((r['query_id'], r['variant']) not in run_keys for r in results):
        raise ValueError('Result without run')
    metrics = []
    for run in runs:
        rows = [r for r in results if (r['query_id'], r['variant']) == (run['query_id'], run['variant'])]
        if len(rows) != int(run['returned_count']) or len(rows) > 5:
            raise ValueError('Invalid returned count')
        if sorted(int(r['rank']) for r in rows) != list(range(1, len(rows) + 1)):
            raise ValueError('Ranks must be contiguous')
        if len({r['product_id'] for r in rows}) != len(rows):
            raise ValueError('Duplicate product in ranking')
        reviewed = [labels[key(r)] for r in rows if labels[key(r)]['relevance'].strip() and labels[key(r)]['reviewer'].strip()]
        complete = run['status'] == 'ok' and (len(reviewed) == len(rows) if rows else bool(queries[run['query_id']]['reviewed_by'].strip()))
        relevant = sum(int(r['relevance']) for r in reviewed) if complete else ''
        metrics.append(dict(query_id=run['query_id'], search_type=queries[run['query_id']]['search_type'],
            variant=run['variant'], status='complete' if complete else ('pending' if run['status']=='ok' else 'unavailable'),
            returned_count=len(rows), annotated_count=len(reviewed), relevant_count=relevant,
            precision_at_5=f'{relevant / 5:.4f}' if complete else 'Pending',
            returned_five=int(len(rows)==5) if run['status']=='ok' else '',
            source_excluded=run['source_excluded']))
    write_csv(directory/'metrics.csv',list(metrics[0]),metrics)
    index={(r['query_id'],r['variant']):r for r in metrics}
    ablation=[]
    for query in queries.values():
        if query['search_type'] != 'image': continue
        q=query['query_id'];a=index[(q,'v1')];b=index[(q,'v2')]
        complete=a['status']==b['status']=='complete'
        ids=lambda variant:[r['product_id'] for r in results if r['query_id']==q and r['variant']==variant]
        successful=a['status']!='unavailable' and b['status']!='unavailable'
        ablation.append(dict(query_id=q,reference_image=query['reference_image'],v1_returned=a['returned_count'],
            v2_returned=b['returned_count'],v1_precision_at_5=a['precision_at_5'],v2_precision_at_5=b['precision_at_5'],
            difference=f"{float(b['precision_at_5'])-float(a['precision_at_5']):.4f}" if complete else 'Pending',
            same_ordered_results=str(ids('v1')==ids('v2')).lower() if successful else 'Unavailable',
            overlap_count=len(set(ids('v1')) & set(ids('v2'))) if successful else '',
            status='complete' if complete else 'pending'))
    write_csv(directory/'ablation.csv',list(ablation[0]),ablation)
    # Primary evaluation has exactly ten cases: v1 is the additional ablation arm.
    primary=[r for r in metrics if r['variant']!='v1']
    groups=[('primary_10',primary),('image_v1',[r for r in metrics if r['variant']=='v1']),
            ('image_v2',[r for r in metrics if r['variant']=='v2'])]
    summary=[]
    for name,rows in groups:
        completed=[r for r in rows if r['status']=='complete']
        available=[r for r in rows if r['status']!='unavailable']
        summary.append(dict(group=name,queries=len(rows),successful_runs=len(available),annotated_queries=len(completed),
            mean_precision_at_5=f"{sum(float(r['precision_at_5']) for r in completed)/len(completed):.4f}" if completed else 'Pending',
            queries_returning_five=sum(r['returned_count']==5 for r in available),
            percent_returning_five=f"{100*sum(r['returned_count']==5 for r in available)/len(available):.2f}" if available else 'Pending'))
    write_csv(directory/'summary.csv',list(summary[0]),summary)
    return metrics, ablation, summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args()
    try:
        _,_,summary=calculate(args.directory)
    except (ValueError,KeyError,FileNotFoundError) as error:
        parser.exit(1,f'Evaluation data error: {error}\n')
    for row in summary: print(row)
    print('CSV metrics updated. Refresh the report tables from these files after human annotation.')
