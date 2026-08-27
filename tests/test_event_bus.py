from atlas.core.event_bus import EventBus


def test_publish_calls_subscriber():

    bus = EventBus()

    received = []

    def handler(payload):
        received.append(payload)

    bus.subscribe(
        "atlas.test",
        handler,
    )

    bus.publish(
        "atlas.test",
        {
            "message": "bonjour",
        },
    )

    assert len(received) == 1

    assert received[0]["message"] == "bonjour"


def test_unsubscribe_removes_handler():

    bus = EventBus()

    received = []

    def handler(payload):
        received.append(payload)

    bus.subscribe(
        "atlas.test",
        handler,
    )

    bus.unsubscribe(
        "atlas.test",
        handler,
    )

    bus.publish(
        "atlas.test",
        "test",
    )

    assert received == []


def test_unknown_event_does_not_crash():

    bus = EventBus()

    bus.publish(
        "event.unknown",
        {
            "test": True,
        },
    )