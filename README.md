# Adam pyRevit Tools

A custom pyRevit toolkit for BIM automation, architectural production, and workflow optimization.

This toolkit focuses on improving real-world Revit workflows through small, reliable, and production-oriented tools — especially in annotation control, family operations, and geometric utilities.

---

## 🚀 Installation

1. Download or clone this repository  
2. Copy the `AdamTools.extension` folder to:
C:\Users<YourUser>\AppData\Roaming\pyRevit\Extensions\

---


3. Reload pyRevit in Revit

---

## 🧰 Toolset Overview

### 🧭 Align Tools

**Align Tag**
- Align selected tags based on user-defined direction  
- Supports consistent annotation layout  

**Align View**
- Align viewports across sheets  
- ✅ Supports **custom tag alignment using bounding box logic**  
- Improved handling for non-standard / custom tag families  

---

### 🧱 Family Tools

**Family Inspector**
- Inspect family instance metadata  
- Identify host, level, and parameter conditions  

**Family Replacement**
- Replace selected family instances  
- Supports controlled placement and transformation logic  

---

### 🪵 Geometry / Utility Tools

**Generate Slat Family**
- Create parametric aluminum slat elements  
- Designed for repeatable façade / ceiling systems  

**Sum Detail Lines**
- Calculate total length of selected detail lines  

---

## ✨ UI / UX Enhancements

- Added **hover-based tooltip previews**
  - Supports **image (`.png`) and video (`.mp4`)**
  - Enhances usability and tool discoverability  

- Improved interaction design for clarity and feedback  

---

## 📦 Version 1.1

### ✨ New Features
- Added Align Tag and Align View tools  
- Added Generate Slat Family tool  
- Added Family Inspector and Family Replacement tools  
- Added Sum Detail Lines tool  

### 🛠 Improvements
- Added **bounding-box-based alignment for custom tags**  
- Added **floating tooltip previews (image + video)**  
- Improved usability and interaction feedback  
- Cleaned and restored repository structure for pyRevit extension packaging  

---

## 🧭 Roadmap

- Batch family replacement workflows  
- Smarter host detection for placement tools  
- Revit agent-assisted workflows (LLM + pyRevit integration)  

---

## 👤 Author

**Adam Zhao**  
Architectural Designer | BIM Automation | Product-Oriented Workflow Development  

---

## 📝 Notes

This toolkit is under active development.

Tools are designed to be:
- **safe**
- **inspectable**
- **production-ready**

The goal is to assist — not replace — human decision-making in BIM workflows.
