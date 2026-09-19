from enviro_data.extraction_plan import plan_site
from enviro_data.habitats import HabitatDomain, normalize_habitat
from enviro_data.input import SiteRecord
from enviro_data.source_catalog import SOURCES, sources_for_habitat
from enviro_data.transforms import apply_source_transform


def site(ecotype: str) -> SiteRecord:
    return SiteRecord("S1", "Test", "TST", 49.0, -123.0, ecotype, 2)


def test_habitat_aliases_are_explicit():
    assert normalize_habitat("river") is HabitatDomain.FRESHWATER
    assert normalize_habitat("marine-freshwater") is HabitatDomain.TRANSITION
    assert normalize_habitat("estuary") is HabitatDomain.TRANSITION
    assert normalize_habitat("pelagic") is HabitatDomain.MARINE
    assert normalize_habitat("mystery") is HabitatDomain.UNKNOWN


def test_source_catalog_ids_and_output_names_are_unique():
    assert len({source.source_id for source in SOURCES}) == len(SOURCES)
    for source in SOURCES:
        names = [variable.output_name for variable in source.variables]
        assert len(names) == len(set(names))
        assert source.documentation_url.startswith("https://")
        for variable in source.variables:
            assert apply_source_transform(1, variable.transform).status == "ok"


def test_sources_route_by_habitat():
    freshwater = {source.source_id for source in sources_for_habitat("freshwater")}
    marine = {source.source_id for source in sources_for_habitat("marine")}
    transition = {source.source_id for source in sources_for_habitat("estuary")}
    assert "merit_hydro_v1_0_1" in freshwater
    assert "noaa_oisst_v2_1" not in freshwater
    assert "noaa_oisst_v2_1" in marine
    assert "merit_hydro_v1_0_1" not in marine
    assert {"merit_hydro_v1_0_1", "noaa_oisst_v2_1"} <= transition


def test_extraction_plan_is_serializable_and_preserves_scale():
    requests = plan_site(site("marine"))
    oisst = next(request for request in requests if request.source_id == "noaa_oisst_v2_1")
    assert oisst.bands == ("sst", "anom", "ice")
    assert oisst.scale_m == 27830
    assert oisst.as_dict()["habitat"] == "marine"
