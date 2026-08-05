"""Rough sonic-lane helpers so recommendations stay in the right genre family."""

from __future__ import annotations

import re
import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


_PUNK_SEEDS = {
    "theoffspring",
    "offspring",
    "greenday",
    "blink182",
    "blink",
    "sum41",
    "goodcharlotte",
    "badreligion",
    "ramones",
    "sexpistols",
    "noirfx",
    "rancid",
    "pennywise",
    "nofx",
    "alkaline",
    "alkalinetrio",
    "newfoundglory",
    "simpleplan",
    "paramore",
    "mychemicalromance",
    "falloutboy",
    "yellowcard",
    "bowlingforsoup",
}

_PUNK_ARTISTS = set(_PUNK_SEEDS) | {
    "fidlar",
    "greenday",
    "blink182",
    "sum41",
    "badreligion",
    "goodcharlotte",
    "nofx",
    "rancid",
    "newfoundglory",
    "simpleplan",
    "panicatthedisco",
}

_POP_ATMOSPHERIC = {
    "lanadelrey",
    "billieeilish",
    "lorde",
    "phoebebridgers",
    "clairo",
    "gracieabrams",
    "taylorswift",
    "oliviarodrigo",
    "sabrinacarpenter",
    "mitski",
    "the1975",
    "beachhouse",
    "cocteautwins",
    "mazzystar",
}

_HIPHOP_SEEDS = {
    "injuryreserve",
    "deathgrips",
    "clipping",
    "jpegmafia",
    "jpegmafia",
    "dannybrown",
    "earlswetheart",
    "earlsweatshirt",
    "tyler",
    "tylerthecreator",
    "kendricklamar",
    "brockhampton",
    "oddfuture",
    "mfdoom",
    "doomtree",
    "runthejewels",
    "armandhammer",
    "opencike",
    "opencike",
    "riitchie",
    "bystorm",
    "amine",
    "aminé",
}

_PUNK_HINT = re.compile(
    r"\b(punk|pop[\s-]?punk|skate[\s-]?punk|hardcore|ska[\s-]?punk|"
    r"offspring|green\s+day|blink[\s-]?182|sum\s*41)\b",
    re.I,
)

_HIPHOP_HINT = re.compile(
    r"\b(hip[\s-]?hop|rap|trap|boom[\s-]?bap|experimental\s+hip|"
    r"injury\s+reserve|death\s+grips|jpegmafia|clipping)\b",
    re.I,
)


def is_punk_lane(seeds: list[str], taste: str = "") -> bool:
    blob = f"{' '.join(seeds)} {taste}"
    if any(_norm(s) in _PUNK_SEEDS for s in seeds):
        return True
    return bool(_PUNK_HINT.search(blob))


def is_hiphop_lane(seeds: list[str], taste: str = "") -> bool:
    blob = f"{' '.join(seeds)} {taste}"
    if any(_norm(s) in _HIPHOP_SEEDS for s in seeds):
        return True
    return bool(_HIPHOP_HINT.search(blob))


def is_atmospheric_pop_artist(artist: str) -> bool:
    return _norm(artist) in _POP_ATMOSPHERIC


def is_punk_artist(artist: str) -> bool:
    return _norm(artist) in _PUNK_ARTISTS


def lane_mismatch(artist: str, seeds: list[str], taste: str = "") -> bool:
    """True if this pick is clearly the wrong sonic lane for the seed."""
    if is_punk_lane(seeds, taste) and is_atmospheric_pop_artist(artist):
        return True
    # Experimental / hip-hop seeds must not get Green Day / pop-punk
    if is_hiphop_lane(seeds, taste) and (
        is_punk_artist(artist) or is_atmospheric_pop_artist(artist)
    ):
        return True
    # Punk seeds must not get random rap headliners from festival sidebars
    if is_punk_lane(seeds, taste) and _norm(artist) in _HIPHOP_SEEDS:
        return True
    return False
