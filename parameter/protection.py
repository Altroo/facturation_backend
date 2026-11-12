"""Prevent parameter removal from clearing saved business selections."""

from rest_framework.exceptions import ValidationError


def ensure_parameter_unused(instance):
    message = f"« {instance.nom} » est déjà utilisé dans un dossier ou un autre enregistrement et ne peut pas être supprimé."
    for relation in instance._meta.get_fields(include_hidden=True):
        if (
            relation.auto_created
            and not relation.concrete
            and relation.related_model is not None
        ):
            if relation.related_model.objects.filter(
                **{relation.field.name: instance.pk}
            ).exists():
                raise ValidationError({"nom": message})

    # Preserve text snapshots on dossiers created before parameter references.
    field = {
        "incoterm": "incoterm",
        "originemarchandise": "origine_marchandise",
        "naturemarchandise": "nature_marchandise",
        "emplacement": "origine_marchandise",
        "marque": "nature_marchandise",
    }.get(instance._meta.model_name)
    if field:
        from logistique.models import LogisticsOrder

        query = {"company_id": instance.company_id, f"{field}__iexact": instance.nom}
        if (
            LogisticsOrder.objects.filter(**query).exists()
            or LogisticsOrder.history.filter(**query).exists()
        ):
            raise ValidationError({"nom": message})
