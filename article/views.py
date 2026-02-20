import csv
import io
from decimal import Decimal, InvalidOperation
from re import search

import openpyxl

from django.db import IntegrityError
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from core.views import CompanyAccessMixin, BaseBulkDeleteView, BaseBulkArchiveView
from core.constants import CURRENCY_CHOICES
from core.permissions import can_create, can_update, can_delete
from core.utils import format_number_with_dynamic_digits
from facturation_backend.utils import CustomPagination
from parameter.models import Marque, Categorie, Unite, Emplacement
from .filters import ArticleFilter
from .models import Article
from .serializers import (
    ArticleSerializer,
    ArticleDetailSerializer,
    ArticleListSerializer,
)
from .utils import get_next_article_reference


class ArticleListCreateView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        archived = self._get_bool_param(request, "archived")
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("Aucun article ne correspond à la requête."))
        try:
            company_id = int(company_id_str)
        except (ValueError, TypeError):
            raise ValidationError({"company_id": _("company_id doit être un entier valide.")})
        self._check_company_access(request, company_id)
        base_queryset = Article.objects.filter(
            company_id=company_id, archived=archived
        ).select_related(
            "company", "marque", "categorie", "emplacement", "unite"
        )
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

        # Check if user has created permission
        if not can_create(request.user, company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour créer un article.")
            )

        serializer = ArticleSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ArticleDetailEditDeleteView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

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

        # Check if user has update permission
        if not can_update(request.user, article.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier cet article.")
            )

        # Check if Commercial is trying to update prix_vente
        if "prix_vente" in request.data and not can_update(
            request.user, article.company_id, "prix_vente"
        ):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier le prix de vente.")
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

        # Check if user has deleted permission
        if not can_delete(request.user, article.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour supprimer cet article.")
            )

        article.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, pk, *args, **kwargs):
        article = self.get_object(pk)
        if not self._has_membership(request.user, article.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier cet article.")
            )

        # Check if user has update permission
        if not can_update(request.user, article.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier cet article.")
            )

        # Check if Commercial is trying to update prix_vente
        if "prix_vente" in request.data and not can_update(
            request.user, article.company_id, "prix_vente"
        ):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier le prix de vente.")
            )

        serializer = ArticleDetailSerializer(
            article, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class GenerateArticleReferenceCodeView(CompanyAccessMixin, APIView):
    """Return the next available ``code_article`` (e.g. ``ART0012``).
    Automatically increases digit count when 9999 is reached."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("company_id manquant dans les paramètres."))

        try:
            company_id = int(company_id_str)
        except (ValueError, TypeError):
            raise Http404(_("company_id doit être un entier valide."))

        if not self._has_membership(request.user, company_id):
            raise PermissionDenied(_("Vous n'avez pas accès à cette société."))

        new_ref = get_next_article_reference(company_id)
        return Response({"reference": new_ref}, status=status.HTTP_200_OK)


class ArchiveToggleArticleView(CompanyAccessMixin, APIView):
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


class ImportArticlesView(CompanyAccessMixin, APIView):
    """Import articles from CSV or Excel files.

    Expected columns: reference, type_article, designation,
    prix_achat, devise_prix_achat, prix_vente, devise_prix_vente,
    tva, remarque, marque, categorie, emplacement, unite.

    Supported formats: .csv, .xls, .xlsx

    - reference: if empty a new ART#### code is generated.
    - FK columns (marque, categorie, emplacement, unite): resolved by
      name; the object is created when it does not exist yet.
    - photo is intentionally not imported.
    """

    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (MultiPartParser,)

    # --------------- helpers ------------------------------------------------

    @staticmethod
    def _get_max_art_number(company_id: int) -> int:
        """Scan existing references to find the highest ART#### number for the given company."""
        max_num = 0
        for ref in Article.objects.filter(
            company_id=company_id, reference__isnull=False
        ).values_list("reference", flat=True):
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
        return max_num

    @staticmethod
    def _resolve_fk(model_class, nom_value, company_id):
        """Return a model instance looked up by *nom* and *company_id*.  Creates it when
        it does not exist.  Returns ``None`` for empty values."""
        if not nom_value or not nom_value.strip():
            return None
        instance, _ = model_class.objects.get_or_create(
            nom=nom_value.strip(), company_id=company_id
        )
        return instance

    @staticmethod
    def _detect_delimiter(sample: str) -> str:
        """Sniff the CSV delimiter; fall back to semicolon (French Excel
        default)."""
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
        except csv.Error:
            return ";"

    @staticmethod
    def _normalize_decimal(value_str: str) -> str:
        """Handle French / European number formatting so that ``Decimal()``
        can parse the result.

        Examples:
            ``"1.000,50"``  -> ``"1000.50"``
            ``"1,000.50"``  -> ``"1000.50"``
            ``"100,50"``    -> ``"100.50"``
            ``"100.50"``    -> ``"100.50"``
        """
        value_str = value_str.strip().replace(" ", "")  # remove thousands spaces
        if "." in value_str and "," in value_str:
            if value_str.rfind(",") > value_str.rfind("."):
                # European: 1.000,50
                value_str = value_str.replace(".", "").replace(",", ".")
            else:
                # US: 1,000.50
                value_str = value_str.replace(",", "")
        elif "," in value_str:
            # Single comma treated as decimal separator
            value_str = value_str.replace(",", ".")
        return value_str

    @staticmethod
    def _parse_file(file) -> list[dict]:
        """Parse CSV or Excel file and return list of row dictionaries."""
        filename = file.name.lower()
        
        if filename.endswith('.csv'):
            # Parse CSV file
            try:
                content = file.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ValueError(_("Le fichier CSV doit être encodé en UTF-8."))
            
            # Detect delimiter
            try:
                dialect = csv.Sniffer().sniff(content[:2048], delimiters=",;\t|")
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ";"
            
            reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
            return list(reader)
        
        elif filename.endswith(('.xls', '.xlsx')):
            # Parse Excel file
            try:
                workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
                sheet = workbook.active
                
                # Get headers from first row
                rows_iter = sheet.iter_rows(values_only=True)
                headers = next(rows_iter, None)
                
                if not headers:
                    raise ValueError(_("Le fichier Excel est vide."))
                
                # Convert to list of dicts
                rows = []
                for row_values in rows_iter:
                    # Skip empty rows
                    if all(v is None or str(v).strip() == "" for v in row_values):
                        continue
                    row_dict = {}
                    for header, value in zip(headers, row_values):
                        if header:
                            # Convert None and numeric values to string
                            if value is None:
                                row_dict[header] = ""
                            else:
                                row_dict[header] = str(value)
                    rows.append(row_dict)
                
                workbook.close()
                return rows
            
            except Exception as e:
                raise ValueError(_(f"Erreur lors de la lecture du fichier Excel : {str(e)}"))
        
        else:
            raise ValueError(_("Format de fichier non supporté. Utilisez .csv, .xls ou .xlsx"))

    # --------------- POST ----------------------------------------------------

    def post(self, request, *args, **kwargs):
        company_id_str = request.data.get("company_id")
        if not company_id_str:
            return Response(
                {"detail": _("Le paramètre company_id est requis.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            company_id = int(company_id_str)
        except (ValueError, TypeError):
            return Response(
                {"detail": _("company_id doit être un entier valide.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        self._check_company_access(request, company_id)

        if not can_create(request.user, company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour créer des articles.")
            )

        file = request.FILES.get("file")
        if not file:
            return Response(
                {"detail": _("Un fichier est requis (CSV ou Excel).")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- parse file ------------------------------------------------------
        try:
            rows = self._parse_file(file)
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        if not rows:
            return Response(
                {"detail": _("Le fichier est vide ou ne contient pas de données.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- iterate ---------------------------------------------------------
        next_num = self._get_max_art_number(company_id) + 1
        errors: list[dict] = []
        created_count = 0

        for idx, row in enumerate(rows, start=2):  # row 1 is the header
            # normalize keys to lowercase, stripped
            normalized_row: dict[str, str] = {
                k.strip().lower(): (v or "").strip()
                for k, v in row.items()
                if k is not None
            }

            # --- required: designation --------------------------------------
            designation = normalized_row.get("designation", "")
            if not designation:
                errors.append(
                    {"row": idx, "message": "La désignation est obligatoire."}
                )
                continue

            # --- type_article ------------------------------------------------
            type_article_raw = normalized_row.get("type_article", "")
            if type_article_raw:
                type_article = type_article_raw.strip().capitalize()
                if type_article not in ("Produit", "Service"):
                    errors.append(
                        {
                            "row": idx,
                            "message": (
                                f"type_article invalide : '{type_article_raw}'."
                                " Utilisez 'Produit' ou 'Service'."
                            ),
                        }
                    )
                    continue
            else:
                type_article = "Produit"

            # --- reference ---------------------------------------------------
            reference = normalized_row.get("reference", "")
            if not reference:
                reference = f"ART{format_number_with_dynamic_digits(next_num)}"
                next_num += 1
            else:
                # keep next_num in sync so auto-generated codes don't clash
                m = search(r"ART(\d+)", reference)
                if m:
                    ref_num = int(m.group(1))
                    if ref_num >= next_num:
                        next_num = ref_num + 1

            # --- decimal fields ----------------------------------------------
            decimal_fields = {"prix_achat": "0", "prix_vente": "0", "tva": "20"}
            decimal_values: dict[str, Decimal] = {}
            decimal_error = False
            for field_name, default in decimal_fields.items():
                raw = normalized_row.get(field_name, default) or default
                try:
                    value = Decimal(self._normalize_decimal(raw))
                    # Round to 2 decimal places for prices and TVA
                    decimal_values[field_name] = value.quantize(Decimal('0.01'))
                except InvalidOperation:
                    errors.append(
                        {
                            "row": idx,
                            "message": f"{field_name} invalide : '{raw}'.",
                        }
                    )
                    decimal_error = True
                    break
            if decimal_error:
                continue

            remarque = normalized_row.get("remarque", "") or None

            # --- devise_prix_achat -------------------------------------------
            valid_currencies = {c[0] for c in CURRENCY_CHOICES}
            devise_achat_raw = normalized_row.get("devise_prix_achat", "").strip().upper()
            if devise_achat_raw and devise_achat_raw not in valid_currencies:
                errors.append(
                    {
                        "row": idx,
                        "message": (
                            f"devise_prix_achat invalide : '{devise_achat_raw}'."
                            f" Utilisez l'une de : {', '.join(sorted(valid_currencies))}."
                        ),
                    }
                )
                continue
            devise_prix_achat = devise_achat_raw or "MAD"

            # --- devise_prix_vente -------------------------------------------
            devise_vente_raw = normalized_row.get("devise_prix_vente", "").strip().upper()
            if devise_vente_raw and devise_vente_raw not in valid_currencies:
                errors.append(
                    {
                        "row": idx,
                        "message": (
                            f"devise_prix_vente invalide : '{devise_vente_raw}'."
                            f" Utilisez l'une de : {', '.join(sorted(valid_currencies))}."
                        ),
                    }
                )
                continue
            devise_prix_vente = devise_vente_raw or "MAD"

            # --- foreign keys ------------------------------------------------
            marque = self._resolve_fk(Marque, normalized_row.get("marque"), company_id)
            categorie = self._resolve_fk(Categorie, normalized_row.get("categorie"), company_id)
            emplacement = self._resolve_fk(
                Emplacement, normalized_row.get("emplacement"), company_id
            )
            unite = self._resolve_fk(Unite, normalized_row.get("unite"), company_id)

            # --- create ------------------------------------------------------
            try:
                Article.objects.create(
                    company_id=company_id,
                    reference=reference,
                    designation=designation,
                    type_article=type_article,
                    prix_achat=decimal_values["prix_achat"],
                    devise_prix_achat=devise_prix_achat,
                    prix_vente=decimal_values["prix_vente"],
                    devise_prix_vente=devise_prix_vente,
                    tva=decimal_values["tva"],
                    remarque=remarque,
                    marque=marque,
                    categorie=categorie,
                    emplacement=emplacement,
                    unite=unite,
                )
                created_count += 1
            except IntegrityError:
                errors.append(
                    {
                        "row": idx,
                        "message": f"Référence '{reference}' déjà utilisée.",
                    }
                )

        response_data = {"total": len(rows), "created": created_count, "errors": errors}
        if errors and created_count == 0:
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
        elif errors:
            return Response(response_data, status=status.HTTP_207_MULTI_STATUS)
        return Response(response_data, status=status.HTTP_200_OK)


class SendCSVExampleEmailView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def post(request, *args, **kwargs):
        """Send import guide via email with CSV and Excel templates attached."""
        from account.tasks import send_csv_example_email
        
        company_id = request.data.get("company_id")
        if not company_id:
            raise PermissionDenied(
                _("L'ID de la société est requis.")
            )
        
        # Check if user has access to this company
        if not Membership.objects.filter(
            user=request.user, company_id=company_id
        ).exists():
            raise PermissionDenied(
                _("Vous n'avez pas accès à cette société.")
            )
        
        # Send email via Celery
        send_csv_example_email.apply_async(
            (request.user.pk, request.user.email)
        )
        
        return Response(
            {"message": "Email envoyé avec succès."},
            status=status.HTTP_200_OK
        )


class BulkDeleteArticleView(BaseBulkDeleteView):
    model = Article
    document_name = "article"

    def get_queryset_with_related(self, ids):
        return Article.objects.filter(pk__in=ids)

    def get_company_id(self, obj):
        return obj.company_id


class BulkArchiveArticleView(BaseBulkArchiveView):
    model = Article
    document_name = "article"

    def get_queryset_with_related(self, ids):
        return Article.objects.filter(pk__in=ids)

    def get_company_id(self, obj):
        return obj.company_id
