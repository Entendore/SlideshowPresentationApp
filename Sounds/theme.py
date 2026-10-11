# theme.py
from typing import Dict, Any

DEFAULT_THEME: Dict[str, Any] = {
    "name": "default-dark",
    "list": {
        "background": "#1e1e1e",
        "border": "1px solid #3e3e42",
    },
    "list_item": {
        "background": "#252526",
        "background_selected": "#2b3a42",
        "border_bottom": "1px solid #333333",
        "border_selected": "1px solid #444444",
        "border_radius": 6,
        "margin": "2px 4px",
        "height": 72,
    },
    "status_strip": {
        "width": 6,
        "border_radius": "5px 0 0 5px",
        "colors": {
            "default": "#666666",
            "rendering": "#0078d4",
            "queued": "#f57c00",
            "ready": "#2e7d32",
            "error": "#d32f2f",
            "unknown": "#616161",
        },
    },
    "badge": {
        "width": 90,
        "height": 28,
        "border_radius": 4,
        "font_size": 11,
        "font_weight": "bold",
        "colors": {
            "default_bg": "#444444",
            "default_text": "#ffffff",
            "default_border": "#555555",
        },
    },
    "text": {
        "title": {
            "color": "#ffffff",
            "font_size": 14,
            "font_weight": "bold",
        },
        "meta": {
            "color": "#00e5ff",
            "font_size": 12,
            "font_weight": "600",
            "color_error": "#ff5252",
        },
    },
    "content_margins": [14, 6, 14, 6],
    "content_spacing": 12,
}

LIGHT_THEME: Dict[str, Any] = {
    "name": "light",
    "list": {
        "background": "#f5f5f5",
        "border": "1px solid #cccccc",
    },
    "list_item": {
        "background": "#ffffff",
        "background_selected": "#e0f2ff",
        "border_bottom": "1px solid #e0e0e0",
        "border_selected": "1px solid #81d4fa",
        "border_radius": 8,
        "margin": "4px 6px",
        "height": 80,
    },
    "status_strip": {
        "width": 6,
        "border_radius": "6px 0 0 6px",
        "colors": {
            "default": "#cccccc",
            "rendering": "#0288d1",
            "queued": "#f57c00",
            "ready": "#388e3c",
            "error": "#d32f2f",
            "unknown": "#9e9e9e",
        },
    },
    "badge": {
        "width": 90,
        "height": 28,
        "border_radius": 4,
        "font_size": 11,
        "font_weight": "bold",
        "colors": {
            "default_bg": "#eeeeee",
            "default_text": "#212121",
            "default_border": "#bdbdbd",
        },
    },
    "text": {
        "title": {
            "color": "#212121",
            "font_size": 14,
            "font_weight": "bold",
        },
        "meta": {
            "color": "#0097a7",
            "font_size": 12,
            "font_weight": "600",
            "color_error": "#d32f2f",
        },
    },
    "content_margins": [14, 8, 14, 8],
    "content_spacing": 12,
}

THEMES = {
    "default-dark": DEFAULT_THEME,
    "light": LIGHT_THEME,
}

_current_theme: Dict[str, Any] = DEFAULT_THEME

def set_theme(name: str):
    global _current_theme
    if name not in THEMES: raise KeyError(f"Unknown theme: {name!r}. Available: {list(THEMES)}")
    _current_theme = THEMES[name]

def get_theme() -> Dict[str, Any]:
    return _current_theme

def list_themes() -> list[str]:
    return list(THEMES.keys())

def list_widget_stylesheet_from_theme() -> str:
    th = get_theme()
    list_th = th["list"]
    item_th = th["list_item"]
    selected_bg = item_th["background_selected"]
    selected_border = item_th["border_selected"]

    return f"""
    QListWidget {{
        background-color: {list_th["background"]};
        border: {list_th["border"]};
        outline: none;
    }}
    QListWidget::item {{
        padding: 2px 4px;
        margin-bottom: 2px;
        border-radius: {item_th["border_radius"]}px;
        background-color: transparent;
    }}
    QListWidget::item:selected {{
        background-color: {selected_bg};
        color: white;
        border: {selected_border};
    }}
    QListWidget::item:hover:!selected {{
        background-color: {item_th["background"]};
    }}
    """