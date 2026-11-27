# Theme Manager

[![QGIS Plugin](https://img.shields.io/badge/QGIS-Plugin-green)](https://plugins.qgis.org/plugins/theme_manager/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](https://www.gnu.org/licenses/quick-guide-gplv3.en.html)
[![Version](https://img.shields.io/badge/version-2.0-orange)](https://github.com/AntoElCrackito/theme_manager_QGIS_plugin)

## 📑 Table des matières / Table of content

- [🇫🇷 Français](#français)
  - [Description](#description)
  - [Fonctionnalités principales](#-fonctionnalités-principales)
  - [Installation](#-installation)
  - [Contact (FR)](#-contact-fr)
- [🇬🇧 English](#english)
  - [Description](#description-1)
  - [Main functionalities](#-main-functionalities)
  - [Install](#-install)
  - [Contact (EN)](#-contact-en)



---

<details open>
<summary><strong>🇫🇷 Français</strong></summary>

## Français

### Description

**Theme Manager** est un plugin développé pour QGIS permettant de visualiser la répartition des affichages des couches par thème dans un projet QGIS. Il permet également de créer ou supprimer des thèmes.

Initialement, ce plugin a été développé durant un stage de fin d'étude au sein du Service Départemental d'Incendie et de Secours du Gard (SDIS30) sur demande du service SIG. En effet, ce dernier met à disposition de nombreux projets sur son portail OpenSIS30 (Portail webmapping Lizmap) et doit gérer des thèmes dans lesquels de nombreuses couches doivent être affichées. Toutefois, QGIS ne permet pas de bénéficier d'une interface graphique pour consulter quelles sont les couches présentes dans chaque thème. Avant que ce plugin soit développé, il était nécessaire d'appliquer chaque thème au projet et de s'assurer de l'apparition de chaque couche une par une. Ce plugin permet de gérer cela avec une interface graphique et un système de case à cocher.

---

### 👨‍💻 Fonctionnalités principales

- Liste des thèmes filtrable, triée naturellement (« Thème 2 » avant « Thème 10 »), adaptée aux projets contenant des dizaines de thèmes.
- Arbre des couches identique au panneau **Couches** de QGIS : cases à cocher pour les couches **et les groupes**, couches grisées sous un groupe décoché, Ctrl+clic pour basculer toute une branche, Espace pour basculer la sélection.
- Sélection de plusieurs thèmes (Ctrl/Maj + clic) : une colonne par thème pour les comparer et les modifier côte à côte, filtre « Différences entre thèmes ».
- Créer, dupliquer, renommer (F2), remplacer par la carte actuelle, supprimer (Suppr) des thèmes ; appliquer un thème par double-clic.
- Style de couche propre à chaque thème (menu contextuel).
- **Réparation des thèmes** : quand un groupe est renommé ou déplacé, les thèmes sont mis à jour automatiquement ; quand une couche est supprimée puis rajoutée, le plugin propose de la remettre dans ses thèmes (bouton « Réparer les thèmes » pour les cas restants).
- Export / import XML de plusieurs thèmes (format compatible avec les versions précédentes), un seul dialogue d'association des couches, mots de passe retirés des sources exportées.
- Fenêtre non modale : QGIS reste utilisable pendant que le gestionnaire est ouvert.
- Compatible QGIS 3.22+ et QGIS 4 (Qt 6).

---

### 📶 Installation

#### Depuis QGIS (https://plugins.qgis.org/plugins/theme_manager/) :

1. Ouvrez QGIS
2. Allez dans `Extensions` > `Installer/Gérer les extensions`
3. Recherchez `Theme Manager`
4. Cliquez sur `Installer`

#### Depuis votre ordinateur :

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

### 📧 Contact (FR)
Sentez-vous libre de me contacter à ce mail : theme.manager.qgis.plugin@gmail.com

Au plaisir d'échanger avec vous !

</details>

---

<details open>
<summary><strong>🇬🇧 English</strong></summary>

## English

### Description

**Theme Manager** is a plugin developed for QGIS which allows you to see which layer of your project is visible in which theme. It also allows you to create, rename or remove themes.

At first, this plugin was developed during an internship at the Service Départemental d'Incendie et de Secours (SDIS30) at one of the GIS department's requests. The SDIS30 provides a number of projects on its OpenSIS30 web portal (Lizmap webmapping platform) and has to manage themes in which a large number of layers need to be displayed. However, QGIS does not provide a graphical interface for checking which layers are present in which theme(s). Before this plugin was developed, it was necessary to apply each theme to the project and ensure that each layer was displayed one by one. This plugin manages this with a graphical interface and a checkbox system.

---

### 👨‍💻 Main functionalities

- Filterable theme list with natural sorting ("Theme 2" before "Theme 10"), designed for projects with dozens of themes.
- Layer tree drawn like the QGIS **Layers** panel: check boxes for layers **and groups**, layers greyed out under an unchecked group, Ctrl+click to switch a whole branch, Space to toggle the selection.
- Select several themes (Ctrl/Shift + click): one column per theme to compare and edit them side by side, "Differences between themes" filter.
- Create, duplicate, rename (F2), replace with the current map, delete (Del) themes; double-click to apply a theme.
- Per-theme layer style (context menu).
- **Theme repair**: when a group is renamed or moved, themes are updated automatically; when a layer is removed and added again, the plugin offers to put it back into its themes ("Repair themes" button for the remaining cases).
- XML export / import of several themes (format compatible with previous versions), a single layer mapping dialog, passwords removed from exported data sources.
- Non-modal window: QGIS stays usable while the manager is open.
- QGIS 3.22+ and QGIS 4 (Qt 6) compatible.

### 🌐 Translations

User visible strings are in English (context `ThemeManager`). After changing them, run `python scripts/update_translations.py` to update `i18n/*.ts` and compile the `*.qm` files (no Qt tools required).

---

### 📶 Install

#### From QGIS Plugins Manager (https://plugins.qgis.org/plugins/theme_manager/)

1. Open QGIS
2. Go `Plugins` > `Install/Manage plugins`
3. Search `Theme Manager`
4. Click `Install`

#### From your computer files :

1. Download the plugin folder from this page.
2. Unzip it.
3. Rename the directory : "theme_manager".
4. Move the directory to the appropriate location :
   - **For Windows :**
     Move `theme_manager` in this directory :
     ```
     DISK:\Users\**YOUR_USERNAME**\AppData\Roaming\QGIS\QGIS3\profiles\**YOUR_QGIS_PROFILE** (usually "default")\python\plugins\theme_manager
     ```
   - **For Linux :**
     Use the following command :
     ```bash
     sudo mv ~/Downloads/theme_manager ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
     ```
---

### 📧 Contact (EN)
Feel free to contact me at : theme.manager.qgis.plugin@gmail.com

Happy to discuss further with you !

</details>
