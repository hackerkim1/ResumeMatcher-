import pytest

from resume_matcher.tracks import TRACKS, all_keywords, keywords_for, track_of


def test_there_are_several_tracks_each_with_keywords():
    assert len(TRACKS) >= 6
    assert all(keywords for keywords in TRACKS.values())


def test_every_keyword_is_a_non_empty_string():
    assert all(isinstance(k, str) and k.strip() for k in all_keywords())


def test_a_keyword_belongs_to_exactly_one_track():
    keywords = all_keywords()
    assert len(keywords) == len(set(keywords))


def test_track_of_finds_the_track_of_a_keyword():
    track, keywords = next(iter(TRACKS.items()))
    assert track_of(keywords[0]) == track


def test_track_of_unknown_keyword_is_none():
    assert track_of("不存在的关键词") is None
    assert track_of(None) is None


def test_keywords_for_returns_the_keywords_of_one_track():
    track, keywords = next(iter(TRACKS.items()))
    assert keywords_for(track) == keywords


def test_keywords_for_unknown_track_lists_the_valid_ones():
    with pytest.raises(ValueError) as e:
        keywords_for("不存在的方向")
    assert next(iter(TRACKS)) in str(e.value)
