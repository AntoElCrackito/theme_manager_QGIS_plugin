# Theme Manager

[![QGIS Plugin](https://img.shields.io/badge/QGIS-Plugin-green)](https://plugins.qgis.org/plugins/theme_manager/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](https://www.gnu.org/licenses/quick-guide-gplv3.en.html)
[![Version](https://img.shields.io/badge/version-1.0.0-orange)](https://github.com/AntoElCrackito/theme_manager_QGIS_plugin)

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

- Créer un thème.
- Supprimer un thème.
- Filtrer la liste des thèmes affichés dans la gestion des couches par thèmes.
- Choisir les couches à afficher par thème.
- Bénéficier d'un sélecteur de thème intégré à la fenêtre du plugin.
- ➕ Interface graphique simple et intuitive.
- ➕ Compatible avec QGIS 3.x.

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

### 🦺 Information importante

Actuellement, il n'est pas possible de gérer les groupes de la même manière que les couches. Je n'ai pas réussi à identifier dans la documentation de l'API QGIS un identifiant ou une variable permettant d'agir sur le statut d’un groupe. J'avais précédemment réussi à le faire, mais une fois le groupe réactivé, les couches apparaissaient grisées et invisibles (comme si une échelle de rendu non satisfaite était définie). Une issue sera prochainement déposée sur la page GitHub de QGIS pour tenter de résoudre ce problème. Si vous trouvez une solution, n'hésitez pas à la partager !

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

- Create a theme.
- Delete a theme.
- Filter the list of themes displayed in the layer management by theme section.
- Select the layers to display by theme.
- Provide a built-in theme selector within the plugin window.
- ➕ Simple and intuitive graphical interface.
- ➕ QGIS 3.x compatible.

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

### 🦺 Important information

At the moment, it's not possible to manage groups in the same way as individual layers. I haven't been able to find an ID or variable in the QGIS API documentation that allows control over a group's visibility status. I previously managed to toggle group visibility, but when reactivated, the layers appeared greyed out and invisible — as if an unmet scale range was applied. An issue will soon be submitted to the QGIS GitHub page to try and resolve this. If you find a solution, feel free to share it!

</details>
