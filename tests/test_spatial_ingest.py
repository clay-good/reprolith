"""Reading an SBML L3 *spatial* model (spec: spatial-class; roadmap's last parked ingestion gap).

The roadmap recorded spatial ingestion as blocked because "there is no standard single-file
interchange format for a reaction-diffusion model to ingest". There is one — the SBML Level 3
`spatial` package — and the pinned libSBML reads it. What was actually missing is narrower and is
still true: no published spatial model is in this corpus, and none can be fetched here.

So the fixtures below are written through **libSBML's own spatial API** rather than by hand. That
makes the spec's reference implementation the writer of every file this reader reads, which is a
real check on the reading path — and still a weaker claim than the other five ingesters can make,
because none of these files came from the field.

Needs the engine extra.
"""

from __future__ import annotations

import pytest

libsbml = pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

from reprolith import ingest_spatial_sbml  # noqa: E402


def _model(
    *,
    axes: int = 1,
    isotropic: bool = True,
    spatial_species: bool = True,
    with_diffusion: bool = True,
    initial_concentration: float | None = 1.0,
    coordinate_system: int | None = None,
    boundary: tuple[int, float] | None = None,
    extent: tuple[float, float] = (0.0, 10.0),
) -> str:
    """An SBML spatial model, assembled with libSBML's own spatial API."""
    document = libsbml.SBMLDocument(libsbml.SBMLNamespaces(3, 1, "spatial", 1))
    document.setPackageRequired("spatial", True)
    model = document.createModel()

    compartment = model.createCompartment()
    compartment.setId("cell")
    compartment.setConstant(True)
    compartment.setSize(1.0)
    compartment.setSpatialDimensions(axes)

    species = model.createSpecies()
    species.setId("U")
    species.setCompartment("cell")
    species.setHasOnlySubstanceUnits(False)
    species.setBoundaryCondition(False)
    species.setConstant(False)
    if initial_concentration is not None:
        species.setInitialConcentration(initial_concentration)
    species.getPlugin("spatial").setIsSpatial(spatial_species)

    if with_diffusion:
        parameter = model.createParameter()
        parameter.setId("D_U")
        parameter.setValue(0.1)
        parameter.setConstant(True)
        coefficient = parameter.getPlugin("spatial").createDiffusionCoefficient()
        coefficient.setVariable("U")
        coefficient.setType(
            libsbml.SPATIAL_DIFFUSIONKIND_ISOTROPIC
            if isotropic
            else libsbml.SPATIAL_DIFFUSIONKIND_ANISOTROPIC
        )
        if not isotropic:
            coefficient.setCoordinateReference1(libsbml.SPATIAL_COORDINATEKIND_CARTESIAN_X)

    if boundary is not None:
        kind, value = boundary
        wall = model.createParameter()
        wall.setId("bc_U")
        wall.setValue(value)
        wall.setConstant(True)
        condition = wall.getPlugin("spatial").createBoundaryCondition()
        condition.setVariable("U")
        condition.setType(kind)
        condition.setCoordinateBoundary("xmin")

    geometry = model.getPlugin("spatial").createGeometry()
    geometry.setCoordinateSystem(
        libsbml.SPATIAL_GEOMETRYKIND_CARTESIAN if coordinate_system is None else coordinate_system
    )
    for index, kind in enumerate(
        (libsbml.SPATIAL_COORDINATEKIND_CARTESIAN_X, libsbml.SPATIAL_COORDINATEKIND_CARTESIAN_Y)[:axes]
    ):
        component = geometry.createCoordinateComponent()
        component.setId("xy"[index])
        component.setType(kind)
        low = component.createBoundaryMin()
        low.setId(f"{'xy'[index]}min")
        low.setValue(extent[0])
        high = component.createBoundaryMax()
        high.setId(f"{'xy'[index]}max")
        high.setValue(extent[1])
    domain_type = geometry.createDomainType()
    domain_type.setId("dt_cell")
    domain_type.setSpatialDimensions(axes)
    domain = geometry.createDomain()
    domain.setId("cell_domain")
    domain.setDomainType("dt_cell")

    text: str = libsbml.writeSBMLToString(document)
    assert document.getNumErrors() == 0, "the fixture itself is not valid SBML"
    return text


def test_a_one_dimensional_model_reads_what_the_solver_runs() -> None:
    model = ingest_spatial_sbml(_model())
    assert model.species == ("U",)
    assert model.diffusivity_of("U") == pytest.approx(0.1)
    assert model.initial == (("U", 1.0),)
    # The extent is the domain the file states, so a caller's dx comes from a stated length.
    assert model.extent == (10.0,)


def test_two_dimensions_read_both_axes() -> None:
    model = ingest_spatial_sbml(_model(axes=2, extent=(0.0, 4.0)))
    assert model.extent == (4.0, 4.0)


def test_the_dossier_records_the_domain_as_stated_because_it_is() -> None:
    """The class records an unstated domain as a load-bearing gap — that is what a *paper* leaves
    out. A file carrying a geometry states it, and a gap here would report the artifact as missing
    something it ships."""
    dossier = ingest_spatial_sbml(_model()).dossier("synthetic", source_location="model.xml")
    assert dossier.state_variables == ("U",)
    assert [gap.element for gap in dossier.load_bearing_gaps()] == []
    assert [p.name for p in dossier.parameters] == ["D_U"]


def test_zero_flux_is_the_one_boundary_condition_this_solver_imposes() -> None:
    ingest_spatial_sbml(_model(boundary=(libsbml.SPATIAL_BOUNDARYKIND_NEUMANN, 0.0)))

    with pytest.raises(ValueError, match="not zero flux"):
        ingest_spatial_sbml(_model(boundary=(libsbml.SPATIAL_BOUNDARYKIND_DIRICHLET, 0.0)))
    with pytest.raises(ValueError, match="not zero flux"):
        ingest_spatial_sbml(_model(boundary=(libsbml.SPATIAL_BOUNDARYKIND_NEUMANN, 2.5)))


def test_an_anisotropic_coefficient_is_a_different_equation() -> None:
    with pytest.raises(ValueError, match="not isotropic"):
        ingest_spatial_sbml(_model(isotropic=False))


def test_a_spatial_species_with_no_diffusion_coefficient_is_refused() -> None:
    with pytest.raises(ValueError, match="declares no diffusion coefficient"):
        ingest_spatial_sbml(_model(with_diffusion=False))


def test_a_species_with_no_uniform_initial_concentration_is_refused() -> None:
    with pytest.raises(ValueError, match="no uniform initial concentration"):
        ingest_spatial_sbml(_model(initial_concentration=None))


def test_a_model_where_nothing_diffuses_is_not_a_reaction_diffusion_model() -> None:
    with pytest.raises(ValueError, match="no species is marked spatial"):
        ingest_spatial_sbml(_model(spatial_species=False, with_diffusion=False))


def test_a_coefficient_for_a_species_that_is_not_spatial_is_refused() -> None:
    """Reading it would report a diffusivity for something the model does not diffuse."""
    with pytest.raises(ValueError, match="does not mark spatial"):
        ingest_spatial_sbml(_model(spatial_species=False))


def test_a_non_cartesian_geometry_is_refused() -> None:
    with pytest.raises(ValueError, match="not Cartesian"):
        ingest_spatial_sbml(
            _model(coordinate_system=libsbml.SPATIAL_GEOMETRYKIND_CARTESIAN + 1)
        )


def test_a_model_with_no_geometry_says_so() -> None:
    document = libsbml.SBMLDocument(libsbml.SBMLNamespaces(3, 1, "spatial", 1))
    document.setPackageRequired("spatial", True)
    document.createModel().createSpecies().setId("U")
    with pytest.raises(ValueError, match="declares no spatial geometry"):
        ingest_spatial_sbml(libsbml.writeSBMLToString(document))


def test_a_domain_that_is_not_a_domain_is_refused() -> None:
    with pytest.raises(ValueError, match="which is not a domain"):
        ingest_spatial_sbml(_model(extent=(3.0, 3.0)))


def test_something_that_is_not_sbml_is_refused() -> None:
    with pytest.raises(ValueError):
        ingest_spatial_sbml("not sbml at all")
