import re
from dataclasses import dataclass

# "Alice: let's ship it" -> ("Alice", "let's ship it"). Speaker names are short, so cap the length
# to avoid treating sentences like "Note to self: ..." as a speaker.
_SPEAKER_LINE = re.compile(r"^\s*([A-Za-z][\w .'-]{0,40}?)\s*:\s+(.+)$")


@dataclass(frozen=True)
class Utterance:
    speaker: str | None
    text: str


@dataclass(frozen=True)
class TextChunk:
    text: str
    speakers: list[str]


def parse_utterances(transcript: str) -> list[Utterance]:
    """Split a transcript into utterances. Lines without a 'Speaker:' prefix continue the previous
    utterance, so pasted paragraphs and wrapped lines both work."""
    utterances: list[Utterance] = []
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _SPEAKER_LINE.match(line)
        if match:
            utterances.append(Utterance(match.group(1).strip(), match.group(2).strip()))
        elif utterances:
            last = utterances[-1]
            utterances[-1] = Utterance(last.speaker, f"{last.text} {line}")
        else:
            utterances.append(Utterance(None, line))
    return utterances


def chunk_transcript(transcript: str, max_chars: int = 800) -> list[TextChunk]:
    """Group consecutive utterances into chunks of roughly `max_chars`, never splitting an
    utterance unless it alone is longer than the limit."""
    chunks: list[TextChunk] = []
    lines: list[str] = []
    speakers: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal lines, speakers, size
        if lines:
            chunks.append(TextChunk("\n".join(lines), speakers))
        lines, speakers, size = [], [], 0

    for utterance in parse_utterances(transcript):
        for piece in _split_long(utterance.text, max_chars):
            line = f"{utterance.speaker}: {piece}" if utterance.speaker else piece
            if size and size + len(line) > max_chars:
                flush()
            lines.append(line)
            size += len(line) + 1
            if utterance.speaker and utterance.speaker not in speakers:
                speakers.append(utterance.speaker)
    flush()
    return chunks


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces, current = [], ""
    for word in text.split():
        if current and len(current) + len(word) + 1 > max_chars:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)
    return pieces
