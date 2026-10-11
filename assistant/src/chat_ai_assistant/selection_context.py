"""Bind explicit numbered result references to the backend's displayed order.

This recognizes bounded English/French ordinal references, not arbitrary user
intent. It never grants access; callers must still apply native authorization.
"""
from datetime import datetime
import re
import unicodedata

ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "premier": 1, "premiere": 1, "deuxieme": 2, "second": 2, "seconde": 2,
    "troisieme": 3, "quatrieme": 4, "cinquieme": 5, "sixieme": 6,
    "septieme": 7, "huitieme": 8, "neuvieme": 9, "dixieme": 10,
}
for _index in range(1, 11):
    for _suffix in ("st", "nd", "rd", "th", "e", "eme", "er", "ere"):
        # Only real English numeric suffixes; French forms remain explicit.
        if _suffix in ("st", "nd", "rd", "th") and _suffix != ({1: "st", 2: "nd", 3: "rd"}.get(_index, "th")):
            continue
        if _suffix in ("er", "ere") and _index != 1:
            continue
        ORDINALS[str(_index) + _suffix] = _index

_QUOTED = re.compile(r'\"[^\"\n]*\"|«[^»\n]*»|“[^”\n]*”|(?<!\w)\x27[^\x27\n]+\x27(?!\w)')


def _target_parts(instruction, aliases, bare_resources=()):
    """Find bounded target references outside quoted/replacement values."""
    text = _QUOTED.sub(" ", instruction)
    text = "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))
    ordinal = r"(" + "|".join(ORDINALS) + r")"
    article = r"\b(?:the|le|la|du|au|ce|cet|cette)\s+"
    command = r"\b(?:delete|archive|update|edit|change|rename|remove|modify|supprime|supprimer|archive|archiver|modifie|modifier|renomme|renommer)\s+(?:(?:the|le|la)\s+)?"
    prefix = r"(?:" + article + "|" + command + ")" + ordinal
    references, explicit, anchors = [], [], []
    for target, nouns in {**aliases, None: r"result|resultat|one|element"}.items():
        for match in re.finditer(prefix + r"\s+(?:" + nouns + r")(?:s)?\b", text):
            references.append((ORDINALS[match.group(1)], target, match.start(), match.end()))
    for match in re.finditer(article + ordinal + r"(?=\s*(?:[.!?,;:]|$))", text):
        references.append((ORDINALS[match.group(1)], None, match.start(), match.end()))
    anchors.extend(end for _, _, _, end in references)
    for target, nouns in aliases.items():
        marker = r"(?:id|identifiant)\s*[:#]?\s*"
        if target in bare_resources:
            marker = r"(?:" + marker + r"|(?:numero|number|no\.|n[°o])\s*[:#]?\s*|#\s*)?"
        pattern = r"\b(?:" + nouns + r")(?:s)?\s+" + marker + r"([1-9][0-9]*)(?=$|\s|[.!?;,:](?:\s|$))"
        for match in re.finditer(pattern, text):
            explicit.append((target, int(match.group(1)), match.start(), match.end()))
            anchors.append(match.end())
        for match in re.finditer(r"\b(?:this|current|ce|cet|cette)\s+(?:" + nouns + r")\b", text):
            anchors.append(match.end())
    # Full resource phrases win over contained nouns: "facture client ID 311"
    # names an invoice, not a second client target. Equal ambiguous spans remain.
    explicit = [value for value in explicit if not any(
        other[2] <= value[2] and value[3] <= other[3] and other[2:] != value[2:]
        for other in explicit)]
    # Exclude replacement text only AFTER an identified target. Introductory
    # 'I want to ...', 'en fait ...', 'Please do this: ...' remain intact.
    cutoff = len(text)
    fields = r"name|nom|title|titre|description|notes?|status|statut|priority|priorite|city|ville|address|adresse|contact|telephone|phone|e-?mail|specialite|specialty|amount|montant|date|comments?|commentaires?"
    markers = r"\b(?:to|en|par)\s+|\s+=\s+|:\s+(?=(?:" + fields + r")\b)|\b(?:" + fields + r")\s*[:=]\s*"
    for match in re.finditer(markers, text):
        if any(end <= match.start() for end in anchors):
            cutoff = match.start()
            break
    return ([(index, target) for index, target, start, _ in references if start < cutoff],
            [(target, value) for target, value, start, _ in explicit if start < cutoff])


def explicit_target_matches(instruction, resource, identifier, aliases, bare_resources=()):
    """None without an explicit ID; otherwise require one matching resource/ID.

    This is request binding, never authorization. Bare identifiers are recognized
    only for application-declared resources without separate business numbers.
    Conflicting targets reject; native permission and confirmation checks remain.
    """
    if not isinstance(instruction, str):
        return None
    _, explicit = _target_parts(instruction, aliases, bare_resources)
    if not explicit:
        return None
    return type(identifier) is int and identifier > 0 and set(explicit) == {(resource, identifier)}


def ordinal_target_matches(instruction, resource, identifier, state, now, aliases):
    """Return None without an explicit ordinal, else require the exact fresh ID.

    Aliases are trusted application code, mapping resource names to regex noun
    alternatives. Recognizes definite-article references and command targets;
    quoted text and replacement clauses are excluded from target matching.
    """
    if not isinstance(instruction, str):
        return None
    found, explicit = _target_parts(instruction, aliases)
    if not found:
        return None
    indexes = {index for index, _ in found}
    named = {target for _, target in found if target is not None}
    if len(indexes) != 1 or (named and named != {resource}):
        return False
    index = next(iter(indexes))
    if type(identifier) is not int or not isinstance(state, dict) or state.get("resource") != resource:
        return False
    ids = state.get("ids")
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 10
            or any(type(value) is not int or value <= 0 for value in ids)
            or len(set(ids)) != len(ids) or index > len(ids)):
        return False
    try:
        expiry = datetime.fromisoformat(state["expires_at"])
        if expiry.utcoffset() is None or now.utcoffset() is None or expiry <= now:
            return False
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    # Business numbers deliberately are not interpreted as primary keys here.
    for target, value in explicit:
        if target != resource or value != identifier:
            return False
    return ids[index - 1] == identifier
