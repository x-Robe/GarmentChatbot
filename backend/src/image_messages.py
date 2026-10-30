"""Existing image modification response wording, shared by upload and continuation."""
def _mixed_message(analysis, products):
    intent = analysis["intent"]
    if intent == "unrelated":
        return ("I'm focused on garment and fashion design assistance, so I can't help with "
                "that topic. I can help you explore styles, colors, fits, patterns, or design references.")
    if intent == "clarification":
        return "Please specify the color, pattern, neckline, sleeve, style, or buttons you want to change."
    if intent == "unsupported":
        return ("I can currently change color, pattern, neckline, sleeve, style, or buttons. "
                "Broader aesthetic changes or other preferences in your message aren't supported in image + text search yet."
                + (" Not applied: " + "; ".join(analysis["unsupported_text"]) + "." if analysis["unsupported_text"] else ""))
    labels = []
    for key, value in analysis["overrides"].items():
        labels.extend((["with buttons" if value else "without buttons"] if key == "buttons" else value))
    preferences = ", ".join(labels)
    text = (f"I applied your preferences ({preferences}) and found the closest matching designs."
            if products else f"No designs matched all your requested changes ({preferences}). Try changing a preference.")
    if analysis["unsupported_text"]:
        text += " These additional changes were not applied: " + "; ".join(analysis["unsupported_text"]) + "."
    return text


