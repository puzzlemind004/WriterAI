"""
Machine d'état des chapitres.
Définit tous les états possibles et les transitions autorisées.
"""
from enum import Enum


class ChapterState(str, Enum):
    # Le chapitre est planifié mais rien n'a commencé
    PENDING = "pending"

    # Un agent rédacteur travaille dessus
    WRITING = "writing"

    # Le chapitre rédigé est en attente de critique
    IN_REVIEW = "in_review"

    # Le critique a rendu son verdict, révision demandée
    REVISION_REQUESTED = "revision_requested"

    # L'agent validateur a approuvé le chapitre
    VALIDATED = "validated"

    # L'utilisateur a pris la main sur le chapitre
    USER_EDITING = "user_editing"

    # L'utilisateur a soumis ses modifications, en attente de critique
    AWAITING_REVIEW = "awaiting_review"

    # L'utilisateur a validé lui-même le chapitre
    USER_VALIDATED = "user_validated"

    # Le chapitre est en erreur (trop de révisions, échec LLM...)
    ERROR = "error"


# Transitions autorisées : état_actuel -> [états_suivants_possibles]
ALLOWED_TRANSITIONS: dict[ChapterState, list[ChapterState]] = {
    ChapterState.PENDING: [
        ChapterState.WRITING,
    ],
    ChapterState.WRITING: [
        ChapterState.IN_REVIEW,
        ChapterState.ERROR,
        ChapterState.USER_EDITING,  # L'utilisateur interrompt
    ],
    ChapterState.IN_REVIEW: [
        ChapterState.VALIDATED,
        ChapterState.REVISION_REQUESTED,
        ChapterState.ERROR,
    ],
    ChapterState.REVISION_REQUESTED: [
        ChapterState.WRITING,
        ChapterState.USER_EDITING,  # L'utilisateur préfère corriger lui-même
        ChapterState.ERROR,
    ],
    ChapterState.VALIDATED: [
        ChapterState.USER_EDITING,  # L'utilisateur veut quand même modifier
    ],
    ChapterState.USER_EDITING: [
        ChapterState.AWAITING_REVIEW,
        ChapterState.USER_VALIDATED,
        ChapterState.WRITING,  # L'utilisateur remet en mode automatique
    ],
    ChapterState.AWAITING_REVIEW: [
        ChapterState.IN_REVIEW,
        ChapterState.USER_EDITING,
    ],
    ChapterState.USER_VALIDATED: [
        ChapterState.USER_EDITING,  # Peut rouvrir si besoin
    ],
    ChapterState.ERROR: [
        ChapterState.PENDING,  # Reset manuel possible
        ChapterState.USER_EDITING,
    ],
}


class InvalidTransitionError(Exception):
    def __init__(self, from_state: ChapterState, to_state: ChapterState):
        super().__init__(
            f"Transition invalide : {from_state} → {to_state}. "
            f"Transitions autorisées depuis {from_state} : "
            f"{[s.value for s in ALLOWED_TRANSITIONS.get(from_state, [])]}"
        )


def validate_transition(current: ChapterState, target: ChapterState) -> None:
    """Lève InvalidTransitionError si la transition n'est pas autorisée."""
    if current not in ALLOWED_TRANSITIONS:
        raise InvalidTransitionError(current, target)
    allowed = ALLOWED_TRANSITIONS[current]
    if target not in allowed:
        raise InvalidTransitionError(current, target)


def is_terminal(state: ChapterState) -> bool:
    """Un état terminal est un état où aucune transition automatique n'est prévue."""
    return state in (
        ChapterState.VALIDATED,
        ChapterState.USER_VALIDATED,
        ChapterState.USER_EDITING,
        ChapterState.ERROR,
    )


def is_user_controlled(state: ChapterState) -> bool:
    """Vrai si le chapitre est sous contrôle utilisateur (pas d'agent automatique)."""
    return state in (
        ChapterState.USER_EDITING,
        ChapterState.USER_VALIDATED,
    )
