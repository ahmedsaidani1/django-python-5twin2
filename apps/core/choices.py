from django.db import models


class MerchandiseType(models.TextChoices):
    ALIMENTAIRE = "alimentaire", "Alimentaire"
    FRAIS = "frais", "Produits frais / réfrigérés"
    MATERIAUX = "materiaux", "Matériaux de construction"
    TEXTILE = "textile", "Textile"
    ELECTRONIQUE = "electronique", "Électronique"
    MOBILIER = "mobilier", "Mobilier"
    INDUSTRIEL = "industriel", "Équipement industriel"
    AGRICOLE = "agricole", "Produits agricoles"
    AUTRE = "autre", "Autre"
