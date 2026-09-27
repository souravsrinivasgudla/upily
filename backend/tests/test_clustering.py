from types import SimpleNamespace

from services.clustering import cluster


def _a(i, source, title, lead=""):
    return SimpleNamespace(id=i, source=source, title=title, raw_content=lead, summary=lead)


# Background stories give the TF-IDF weights something to contrast against
BACKGROUND = [
    _a(100 + i, f"Outlet{i}", t) for i, t in enumerate([
        "Floods and landslides kill dozens in Nepal",
        "Central bank holds interest rates steady",
        "New smartphone launch draws long queues",
        "Heatwave warning issued across southern Europe",
        "Film festival opens with a record number of premieres",
    ])
]


def test_same_event_from_different_outlets_is_grouped():
    arts = BACKGROUND + [
        _a(1, "The Verge", "Apple hit with $5.7 billion in damages over haptic patents",
           "A jury ordered Apple to pay $5.7 billion for infringing haptic patents."),
        _a(2, "CNBC", "Apple faces $5.7 billion patent infringement verdict over haptics",
           "Apple must pay $5.7 billion after a jury found it infringed haptic patents."),
    ]
    groups = cluster(arts)
    assert groups[1] == groups[2] == 1


def test_same_outlet_similar_topic_is_not_grouped():
    arts = BACKGROUND + [
        _a(1, "Healthline", "FDA approves new pill for common breast cancer"),
        _a(2, "Healthline", "Star says early breast cancer diagnosis saved her life"),
    ]
    groups = cluster(arts)
    assert groups[1] != groups[2]


def test_one_shared_word_is_not_enough():
    arts = BACKGROUND + [
        _a(1, "TechCrunch", "Meta and YouTube will run ads for Musk documentary"),
        _a(2, "WIRED", "Meta's new chatbot is adults-only"),
    ]
    groups = cluster(arts)
    assert groups[1] != groups[2]


def test_grouping_is_transitive_and_id_is_smallest_member():
    arts = BACKGROUND + [
        _a(7, "NYT", "27 killed in mass shootings in South Africa overnight"),
        _a(3, "BBC", "Two mass shootings in South Africa leave 27 dead"),
        _a(9, "Al Jazeera", "Several killed in South Africa mass shootings"),
    ]
    groups = cluster(arts)
    assert groups[7] == groups[3] == groups[9] == 3
