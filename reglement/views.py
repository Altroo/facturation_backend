from decimal import Decimal

from django.db.models import Sum
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from facturation_backend.utils import CustomPagination
from facture_client.models import FactureClient
from .filters import ReglementFilter
from .models import Reglement
from .serializers import (
    ReglementCreateSerializer,
    ReglementDetailSerializer,
    ReglementListSerializer,
    ReglementUpdateSerializer,
)


class ReglementListCreateView(APIView):
    """
    GET: List règlements with pagination and aggregated stats.
    POST: Create a new règlement.

    Extra fields returned with pagination:
    - chiffre_affaire_total: Total TTC après remise of all factures for the company
    - total_reglements: Sum of all valid règlements for the company
    - total_impayes: chiffre_affaire_total - total_reglements
    """

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _get_bool_param(request, param: str, default: bool = False) -> bool:
        val = request.query_params.get(param, str(default).lower())
        return val.lower() == "true"

    @staticmethod
    def _check_company_access(request, company_id: int) -> None:
        if not Membership.objects.filter(
            user=request.user, company_id=company_id
        ).exists():
            raise PermissionDenied(
                detail=_("Seuls les Admins de cette société peuvent y accéder.")
            )

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        company_id_str = request.query_params.get("company_id")

        if not company_id_str:
            raise Http404(_("company_id est requis."))

        company_id = int(company_id_str)
        self._check_company_access(request, company_id)

        # Get règlements for factures belonging to this company
        base_queryset = Reglement.objects.filter(
            facture_client__client__company_id=company_id
        ).select_related(
            "facture_client",
            "facture_client__client",
            "mode_reglement",
        )

        filterset = ReglementFilter(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")

        # Calculate aggregated stats for the company
        # Chiffre d'affaire total = sum of all factures' total_ttc_apres_remise
        factures = FactureClient.objects.filter(client__company_id=company_id)
        chiffre_affaire_total = factures.aggregate(total=Sum("total_ttc_apres_remise"))[
            "total"
        ] or Decimal("0.00")

        # Total des règlements = sum of all valid règlements
        total_reglements = Reglement.objects.filter(
            facture_client__client__company_id=company_id, statut="Valide"
        ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

        # Total des impayés = CA - règlements
        total_impayes = chiffre_affaire_total - total_reglements

        extra_stats = {
            "chiffre_affaire_total": str(chiffre_affaire_total),
            "total_reglements": str(total_reglements),
            "total_impayes": str(total_impayes),
        }

        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = ReglementListSerializer(
                page, many=True, context={"request": request}
            )
            response = paginator.get_paginated_response(serializer.data)
            response.data.update(extra_stats)
            return response

        serializer = ReglementListSerializer(
            ordered_qs, many=True, context={"request": request}
        )
        return Response(
            {
                "results": serializer.data,
                **extra_stats,
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def post(request, *args, **kwargs):
        facture_client_id = request.data.get("facture_client")

        if not facture_client_id:
            raise PermissionDenied(
                _("Une facture client doit être spécifiée pour le règlement.")
            )

        try:
            facture_client = FactureClient.objects.get(pk=facture_client_id)
        except FactureClient.DoesNotExist:
            raise Http404(_("Facture client introuvable."))

        if not Membership.objects.filter(
            user=request.user, company_id=facture_client.client.company_id
        ).exists():
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à créer un règlement pour cette société.")
            )

        serializer = ReglementCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        response_serializer = ReglementDetailSerializer(
            instance, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ReglementDetailEditDeleteView(APIView):
    """
    GET: Retrieve a règlement with invoice-specific financial info.
    PUT: Update a règlement.
    DELETE: Delete a règlement.

    Extra fields returned:
    - montant_facture: Total TTC après remise of the associated invoice
    - total_reglements_facture: Sum of all valid règlements for the invoice
    - reste_a_payer: montant_facture - total_reglements_facture
    """

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def get_object(pk):
        try:
            return Reglement.objects.select_related(
                "facture_client",
                "facture_client__client",
                "mode_reglement",
            ).get(pk=pk)
        except Reglement.DoesNotExist:
            raise Http404(_("Aucun règlement ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        reglement = self.get_object(pk)

        if not self._has_membership(
            request.user, reglement.facture_client.client.company_id
        ):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à consulter ce règlement.")
            )

        serializer = ReglementDetailSerializer(reglement, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        reglement = self.get_object(pk)

        if not self._has_membership(
            request.user, reglement.facture_client.client.company_id
        ):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier ce règlement.")
            )

        serializer = ReglementUpdateSerializer(
            reglement, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        reglement = self.get_object(pk)

        if not self._has_membership(
            request.user, reglement.facture_client.client.company_id
        ):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à supprimer ce règlement.")
            )

        reglement.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReglementStatusUpdateView(APIView):
    """
    PATCH: Update the status of a règlement (Valide/Annulé).
    """

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def get_object(pk):
        try:
            return Reglement.objects.select_related(
                "facture_client",
                "facture_client__client",
            ).get(pk=pk)
        except Reglement.DoesNotExist:
            raise Http404(_("Aucun règlement ne correspond à la requête."))

    def patch(self, request, pk, *args, **kwargs):
        reglement = self.get_object(pk)

        if not self._has_membership(
            request.user, reglement.facture_client.client.company_id
        ):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier ce règlement.")
            )

        new_status = request.data.get("statut")
        valid_statuses = [choice[0] for choice in Reglement.STATUT_CHOICES]

        if new_status not in valid_statuses:
            raise ValidationError({"statut": _("Statut invalide.")})

        # If changing from Annulé to Valide, validate that the montant
        # doesn't exceed the remaining amount and facture status is valid
        if reglement.statut == "Annulé" and new_status == "Valide":
            # Check facture status
            allowed_statuses = ["Envoyé", "Accepté"]
            if reglement.facture_client.statut not in allowed_statuses:
                raise ValidationError(
                    {
                        "statut": f"Impossible de valider un règlement pour une facture "
                        f"avec le statut '{reglement.facture_client.statut}'. "
                        f"Statuts autorisés: {', '.join(allowed_statuses)}."
                    }
                )

            reste_a_payer = Reglement.get_reste_a_payer(
                reglement.facture_client, exclude_reglement_id=reglement.id
            )
            if reglement.montant > reste_a_payer:
                raise ValidationError(
                    {
                        "statut": f"Impossible de valider ce règlement. "
                        f"Le montant ({reglement.montant} MAD) dépasse "
                        f"le reste à payer ({reste_a_payer} MAD)."
                    }
                )

        reglement.statut = new_status
        reglement.save()

        return Response({"statut": reglement.statut}, status=status.HTTP_200_OK)
