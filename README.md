# Theme Manager

![QGIS Plugin](https://img.shields.io/badge/QGIS-Plugin-green)
![License](https://img.shields.io/badge/license-GPLv3-blue)
![Version](https://img.shields.io/badge/version-1.0.0-orange)

## Description

**Theme Manager** est un plugin développé pour QGIS permettant de visualiser la répartition des affichages des couches par thème dans un projet QGIS. Il permet également de créer ou supprimer des thèmes.

Initialement, ce plugin a été développé durant un stage de fin d'étude au sein du Service Départemental d'Incendie et de Secours du Gard (SDIS30) sur demande du service SIG. En effet, ce dernier met a disposition de nombreux projets sur son portail OpenSIS30 (Portail webmapping Lizmap) et doit gérer des thèmes dans lesquels de nombreuses couches doivent être affichées, toutefois, QGIS ne permet pas de bénéficier d'une interface graphique pour consulter quelles sont les couches présentent dans chaque thème. Avant d'utiliser ce plugin, il était nécessaire d'appliquer chaque thème au projet et s'assurer de l'apparition de chaque couche une par une. Ce plugin permet de gérer cela avec une interface graphique et un système de case à cocher.

---

## 👨‍💻 Fonctionnalités principales

- Créer un thème.
- Supprimer un thème.
- Filtrer la liste des thèmes affichés dans la gestion des couches par thèmes.
- Choisir les couches à afficher par thème.
- Bénéficier d'un sélecteur de thème intégré à la fenêtre du plugin.
- ➕ Interface graphique simple et intuitive.
- ➕ Compatible avec QGIS 3.x.

---

## 📶 Installation

### Depuis QGIS (bientôt disponible)

1. Ouvrez QGIS
2. Allez dans `Extensions` > `Installer/Gérer les extensions`
3. Recherchez `Theme Manager`
4. Cliquez sur `Installer`

### Depuis votre ordinateur :

1. Télécharger le dossier du plugin.
2. S'il est sous format .zip, le dézipper.
3. Renommer le dossier theme_manager
4. Déplacer le répertoire dans l'emplacement approprié :
   - **Pour Windows :**
     Déplacez le dossier `theme_manager` dans le répertoire suivant :
     ```
     DISQUE:\Users\**VOTRE_NOM_D_UTILISATEUR**\AppData\Roaming\QGIS\QGIS3\profiles\**VOTRE_PROFILE_QGIS** (généralement "default")\python\plugins\theme_manager
     ```
   - **Pour Linux :**
     Utilisez la commande suivante pour déplacer le plugin dans le répertoire approprié :
     ```bash
     sudo mv ~/Downloads/theme_manager ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
     ```
---

## 📧 Contact :
Sentez-vous libre de me contacter à ce mail : theme.manager.qgis.plugin@gmail.com

Au plaisir d'échanger avec vous !
