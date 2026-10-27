"""
Auto Maintenance - Exceptions pour l'orchestrateur de workflow.
"""

from __future__ import annotations


class StepError(Exception):
    """Erreur bloquante survenue lors de l'exécution d'une étape du workflow."""
    pass


class WorkflowCancelled(Exception):
    """Le workflow a été interrompu ou annulé à la demande de l'utilisateur."""
    pass
