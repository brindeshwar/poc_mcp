from meeting_hub.chunking import chunk_transcript, parse_utterances


def test_parses_speakers_and_joins_continuation_lines():
    utterances = parse_utterances("Alice: Hello there\nstill Alice talking\n\nBob: Hi")
    assert [(u.speaker, u.text) for u in utterances] == [
        ("Alice", "Hello there still Alice talking"),
        ("Bob", "Hi"),
    ]


def test_plain_text_without_speakers_is_kept():
    utterances = parse_utterances("Just some notes.\nMore notes.")
    assert [(u.speaker, u.text) for u in utterances] == [(None, "Just some notes. More notes.")]


def test_long_sentence_with_colon_is_not_a_speaker():
    line = "We agreed on the following plan for the migration over the next two sprints: phase one"
    assert parse_utterances(line)[0].speaker is None


def test_chunks_respect_size_and_track_speakers():
    transcript = "\n".join(f"Speaker{i % 3}: " + "word " * 40 for i in range(10))
    chunks = chunk_transcript(transcript, max_chars=500)
    assert len(chunks) > 1
    assert all(len(c.text) <= 500 for c in chunks)
    assert {s for c in chunks for s in c.speakers} == {"Speaker0", "Speaker1", "Speaker2"}


def test_oversized_utterance_is_split():
    chunks = chunk_transcript("Alice: " + "longword " * 300, max_chars=200)
    assert len(chunks) > 1
    assert all(c.speakers == ["Alice"] for c in chunks)


def test_empty_transcript_has_no_chunks():
    assert chunk_transcript("   \n  ") == []
