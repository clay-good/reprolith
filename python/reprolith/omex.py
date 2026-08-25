"""Reading a shipped COMBINE archive (catalog-backlog roadmap #4: adopt-and-verify fast-path).

An OMEX / COMBINE archive is the packaged form of everything a paper's simulation needs: a zip
whose ``manifest.xml`` lists each file and says, by format URI, what it is. When a paper ships
one, ingestion has both halves at once — the model, and the SED-ML that says which curves the
paper shows — so :func:`ingest_omex` produces a dossier with structure *and* claims from a single
file (spec: ``paper-ingestion`` — "Artifact intake and typing").

It is plain zip plus XML, so this reader uses only the standard library. It never writes to disk:
members are read by name out of the archive, and nothing in an archive is executed.

What it will not do is guess. An archive that packages several simulation experiments with none
marked master, or whose experiment runs several model files, describes more than one reproduction;
picking one would silently certify a run the archive did not single out. Those are refused with a
message naming the ambiguity rather than resolved.
"""

from __future__ import annotations

import io
import os
import posixpath
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import replace

from .dossier import Dossier, Gap, GapKind, ModelArtifact
from .ingest import ingest_sbml
from .sedml import sedml_model_sources

#: The COMBINE specifications namespace every standard format URI is built on. A format is named
#: by its final segment — ``.../sbml.level-2.version-4`` is SBML, ``.../sed-ml`` is SED-ML — and a
#: format outside this namespace (a PDF, a CSV, a media type URI) is recorded verbatim.
_COMBINE_SPECIFICATIONS = "http://identifiers.org/combine.specifications/"


def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _normalize(location: str) -> str:
    """An archive location as it appears as a zip member name: ``./model.xml`` is ``model.xml``."""
    cleaned = location.strip().lstrip("/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _format_name(format_uri: str) -> str:
    """The short name of a manifest format URI, or the URI itself when it is not a COMBINE one."""
    if not format_uri.startswith(_COMBINE_SPECIFICATIONS):
        return format_uri
    # `sbml.level-2.version-4` and `sbml` are both SBML; the version belongs to the file, not to
    # what kind of thing it is, and the dossier's artifact record answers the second question.
    return format_uri[len(_COMBINE_SPECIFICATIONS):].split(".")[0]


def _read_manifest(archive: zipfile.ZipFile) -> list[tuple[str, str, bool]]:
    """The manifest's contents as ``(location, format name, master)``, in manifest order."""
    try:
        manifest = archive.read("manifest.xml")
    except KeyError:
        raise ValueError(
            "not a COMBINE archive: no manifest.xml at the archive root. A zip of model files "
            "is not an archive — the manifest is what says what each file is."
        ) from None
    try:
        root = ET.fromstring(manifest)
    except ET.ParseError as exc:
        raise ValueError(f"unreadable COMBINE manifest: {exc}") from exc

    contents: list[tuple[str, str, bool]] = []
    for element in root.iter():
        if _localname(element.tag) != "content":
            continue
        location = _normalize(element.get("location", ""))
        if not location or location in (".", "manifest.xml"):
            # The entries describing the archive itself and the manifest listing it: both are the
            # archive's machinery, not files the paper ships. Skipped in both directions, so a
            # manifest that lists itself — as archives conventionally do — and one that does not
            # produce the same set of artifacts.
            continue
        contents.append((
            location,
            _format_name(element.get("format", "")),
            element.get("master", "false").strip().lower() == "true",
        ))
    return contents


def _choose_experiment(contents: list[tuple[str, str, bool]]) -> str | None:
    """The one SED-ML document the archive singles out, or ``None`` when it ships none."""
    sedmls = [location for location, name, _ in contents if name == "sed-ml"]
    if not sedmls:
        return None
    masters = [location for location, name, master in contents if name == "sed-ml" and master]
    if len(masters) == 1:
        return masters[0]
    if len(sedmls) == 1 and not masters:
        return sedmls[0]
    ambiguous = masters or sedmls
    raise ValueError(
        f"the archive does not single out one simulation experiment: {len(ambiguous)} SED-ML "
        f"documents ({', '.join(sorted(ambiguous))}) are "
        + ("all marked master" if masters else "present with none marked master")
        + ". Which one the paper ran is the archive's to say, not ingestion's to guess."
    )


def _resolve(source: str, *, relative_to: str) -> str:
    """A SED-ML model source resolved to an archive member name, relative to the document.

    Archive member names are POSIX paths whatever the host is, so this joins them with
    ``posixpath``: ``os.path`` would build ``experiments\\..\\models\\m.xml`` on Windows and
    match no member. A source that climbs out of the archive root resolves to a name the archive
    does not contain and is refused there; nothing here touches the filesystem.
    """
    base = posixpath.dirname(relative_to)
    return _normalize(posixpath.normpath(posixpath.join(base, _normalize(source))))


def ingest_omex(archive: str | os.PathLike[str] | bytes, *, entry: str) -> Dossier:
    """Ingest a COMBINE archive into a dossier: its model's structure and its document's claims.

    ``archive`` is the ``.omex`` file — a path or its bytes — and ``entry`` is the catalog-entry
    key the dossier belongs to. The archive's ``manifest.xml`` says which member is the SED-ML
    experiment and which is the model; the model is ingested as in :func:`ingest_sbml`, and the
    experiment's plots become the dossier's claims (:func:`reprolith.enumerate_sedml_claims`).

    Every member of the archive is recorded as an artifact with the format the manifest gives it,
    including files ingestion does not read — a PDF, a data table — because the dossier's job is
    to record what the paper ships, not only the parts it understands. A member the manifest does
    not list is recorded too, with the format ``unlisted``: the archive is malformed in that
    respect, and dropping the file would hide it.

    Refused rather than guessed at, each with a message naming the ambiguity: an archive with no
    manifest; one whose SED-ML documents do not single out one experiment; one whose experiment
    runs more than one model file, or one the archive does not contain; and one that ships neither
    a SED-ML nor exactly one SBML model, where there is nothing to say which model the dossier is
    of. A valid archive that ships only a model — no experiment — yields structure and no claims,
    because nothing in it says which results the paper published.
    """
    handle: str | os.PathLike[str] | io.BytesIO
    handle = io.BytesIO(archive) if isinstance(archive, bytes) else archive
    try:
        with zipfile.ZipFile(handle) as zf:
            contents = _read_manifest(zf)
            experiment = _choose_experiment(contents)
            members = zf.namelist()

            sedml_text: str | None = None
            if experiment is not None:
                if experiment not in members:
                    raise ValueError(
                        f"the archive's manifest lists the experiment '{experiment}', "
                        "but the archive does not contain it"
                    )
                sedml_text = zf.read(experiment).decode("utf-8")
                sources = sedml_model_sources(sedml_text)
                resolved = tuple(dict.fromkeys(_resolve(s, relative_to=experiment) for s in sources))
                if len(resolved) != 1:
                    raise ValueError(
                        f"the experiment '{experiment}' runs {len(resolved)} model files "
                        f"({', '.join(resolved) or 'none'}); a dossier is the extraction of one "
                        "model, and which of them the paper's figures came from is the archive's "
                        "to say"
                    )
                model_location = resolved[0]
                if model_location not in members:
                    raise ValueError(
                        f"the experiment '{experiment}' runs '{model_location}', "
                        "which the archive does not contain"
                    )
            else:
                models = [loc for loc, name, _ in contents if name == "sbml"]
                if len(models) != 1:
                    raise ValueError(
                        f"the archive ships no SED-ML experiment and {len(models)} SBML models; "
                        "with no experiment to name the model, only a single-model archive says "
                        "what the dossier is of"
                    )
                model_location = models[0]
                if model_location not in members:
                    raise ValueError(
                        f"the archive's manifest lists the model '{model_location}', "
                        "but the archive does not contain it"
                    )

            model_text = zf.read(model_location).decode("utf-8")
    except zipfile.BadZipFile as exc:
        raise ValueError(f"not a readable COMBINE archive: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"an archive member is not readable text: {exc}") from exc

    dossier = ingest_sbml(
        model_text, entry=entry, source_label=model_location, sedml=sedml_text
    )
    # ingest_sbml records the model it was handed; the archive knows about every other file too,
    # and a member the manifest never listed is still a file the paper shipped.
    listed = {location: name for location, name, _ in contents}
    ingested = {a.filename: a for a in dossier.artifacts}
    artifacts = tuple(
        ingested.get(location) or ModelArtifact(filename=location, detected_format=name)
        for location, name in listed.items()
        if location in members
    ) + tuple(
        ingested.get(member) or ModelArtifact(filename=member, detected_format="unlisted")
        for member in members
        if member not in listed and member != "manifest.xml" and not member.endswith("/")
    )
    # A file the manifest promises and the archive does not ship is missing from the source, so it
    # is a gap. Recording it as an artifact instead would assert the paper ships a file it does
    # not, and dropping it silently would hide that the archive is short of what it lists — which
    # is exactly the kind of omission the "what was missing" report exists to name.
    absent = tuple(
        Gap(
            element=location,
            kind=GapKind.OTHER,
            detail=(
                f"the archive's manifest lists '{location}' as {name}, "
                "but the archive does not contain it"
            ),
        )
        for location, name in listed.items()
        if location not in members
    )
    return replace(dossier, artifacts=artifacts, gaps=dossier.gaps + absent)


__all__ = ["ingest_omex"]
