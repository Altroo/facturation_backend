from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Ville
from .serializers import VilleSerializer


class VilleListCreateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        queryset = Ville.objects.all().order_by("-id")
        serializer = VilleSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @staticmethod
    def post(request, *args, **kwargs):
        serializer = VilleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        raise ValidationError(serializer.errors)


class VilleDetailEditDeleteView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get_object(pk):
        try:
            return Ville.objects.get(pk=pk)
        except Ville.DoesNotExist:
            raise Http404(_("Aucune ville ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        ville = self.get_object(pk)
        serializer = VilleSerializer(ville)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        ville = self.get_object(pk)
        serializer = VilleSerializer(ville, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        raise ValidationError(serializer.errors)

    def delete(self, request, pk, *args, **kwargs):
        ville = self.get_object(pk)
        ville.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
