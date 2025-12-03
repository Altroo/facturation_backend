from re import search

from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from facturation_backend.utils import CustomPagination
from .filters import ArticleFilter
from .models import Article
from .serializers import (
    ArticleSerializer,
    ArticleDetailSerializer,
    ArticleListSerializer,
)


class ArticleListCreateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _get_bool_param(request, param: str, default: bool = False) -> bool:
        """Parse boolean query param safely."""
        val = request.query_params.get(param, str(default).lower())
        return val.lower() == "true"

    @staticmethod
    def _check_company_access(request, company_id: int) -> None:
        """Raise PermissionDenied if user lacks membership for company."""
        if not Membership.objects.filter(
            user=request.user, company_id=company_id
        ).exists():
            raise PermissionDenied(
                detail=_("Seuls les Admins de cette société peuvent y accéder.")
            )

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        archived = self._get_bool_param(request, "archived")
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("Aucun article ne correspond à la requête."))
        company_id = int(company_id_str)
        self._check_company_access(request, company_id)
        base_queryset = Article.objects.filter(company_id=company_id, archived=archived)
        filterset = ArticleFilter(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")
        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = ArticleListSerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        serializer = ArticleListSerializer(
            ordered_qs, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @staticmethod
    def post(request, *args, **kwargs):
        # the article must be created for a company the user belongs to
        company_id = request.data.get("company")
        if (
            not company_id
            or not Membership.objects.filter(
                user=request.user, company_id=company_id
            ).exists()
        ):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à créer un article pour cette société.")
            )
        serializer = ArticleSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ArticleDetailEditDeleteView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        """True if the user has a Membership for the given company."""
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def get_object(pk):
        try:
            return Article.objects.get(pk=pk)
        except Article.DoesNotExist:
            raise Http404(_("Aucun article ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        article = self.get_object(pk)
        if not self._has_membership(request.user, article.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à consulter cet article.")
            )
        serializer = ArticleDetailSerializer(article, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        article = self.get_object(pk)
        if not self._has_membership(request.user, article.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier cet article.")
            )
        serializer = ArticleDetailSerializer(
            article, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        article = self.get_object(pk)
        if not self._has_membership(request.user, article.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à supprimer cet article.")
            )
        article.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, pk, *args, **kwargs):
        article = self.get_object(pk)
        if not self._has_membership(request.user, article.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier cet article.")
            )
        serializer = ArticleDetailSerializer(
            article, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class GenerateArticleReferenceCodeView(APIView):
    """Return the next available ``code_article`` (e.g. ``ART0012``)."""

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        max_num = 0
        for ref in Article.objects.filter(reference__isnull=False).values_list(
            "reference", flat=True
        ):
            if not ref:
                continue
            m = search(r"ART(\d+)", ref)
            if m:
                num_str = m.group(1)
            else:
                m_last = search(r"(\d+)(?!.*\d)", ref)
                num_str = m_last.group(1) if m_last else None
            if not num_str:
                continue
            try:
                value = int(num_str)
            except ValueError:
                continue
            if value > max_num:
                max_num = value

        next_number = max_num + 1
        new_ref = f"ART{next_number:04d}"
        return Response({"reference": new_ref}, status=status.HTTP_200_OK)


class ArchiveToggleArticleView(APIView):
    """Toggle ``archived`` status for an article."""

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _to_bool(value):
        """Convert common string/number representations to a bool."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "y")
        return None

    @staticmethod
    def get_object(pk):
        try:
            return Article.objects.get(pk=pk)
        except Article.DoesNotExist:
            raise Http404(_("Aucun article ne correspond à la requête."))

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    def patch(self, request, pk, *args, **kwargs):
        article = self.get_object(pk)
        if not self._has_membership(request.user, article.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier l'état de cet article.")
            )
        # Determine the desired state
        if "archived" in request.data:
            new_state = self._to_bool(request.data["archived"])
        else:
            # toggle when not explicitly provided
            new_state = not article.archived
        article.archived = new_state
        article.save(update_fields=["archived"])
        serializer = ArticleDetailSerializer(article, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)
