from backend.main import app


def test_new_routes_are_mounted():
    paths = {route.path for route in app.routes}

    assert "/skill-gap/analyze" in paths
    assert "/job-insight/top-matches" in paths
