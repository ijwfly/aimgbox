from aimg.jobs.registry import JobRegistry, discover_handlers


def test_discover_handlers():
    discover_handlers()
    assert "remove_bg" in JobRegistry.all()


def test_handler_info():
    discover_handlers()
    info = JobRegistry.get("remove_bg")
    assert info is not None
    assert info.slug == "remove_bg"
    assert info.name == "Remove Background"
    assert info.handler_fn is not None
    assert info.input_model is not None
    assert info.output_model is not None


def test_txt2img_discovered():
    discover_handlers()
    assert "txt2img" in JobRegistry.all()
    info = JobRegistry.get("txt2img")
    assert info is not None
    assert info.name == "Text to Image"
    assert info.input_model is not None
    assert info.output_model is not None


def test_get_nonexistent():
    assert JobRegistry.get("nonexistent_handler_xyz") is None
