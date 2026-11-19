import re

# common prompt injection phrases, checked before calling the model
BLOCKED_PHRASES = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore your instructions",
    "ignore the above",
    "disregard your rules",
    "forget your rules",
    "system prompt",
    "reveal your prompt",
    "show your prompt",
    "developer mode",
    "jailbreak",
    "act as dan",
]


def is_blocked(question):
    text = question.lower()
    for phrase in BLOCKED_PHRASES:
        if phrase in text:
            return True
    return False


def find_urls(text):
    return re.findall(r"https?://[^\s\"'<>)\]]+", text)


def remove_unknown_links(answer, allowed_urls):
    # keep markdown links only if the url came from a tool result, otherwise keep just the text
    removed = []

    def check_link(match):
        link_text = match.group(1)
        url = match.group(2).strip()
        if url in allowed_urls:
            return match.group(0)
        removed.append(url)
        return link_text

    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", check_link, answer)
    return cleaned, removed
