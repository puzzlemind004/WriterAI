"""
Gestion des fichiers markdown du projet (lorebook + chapitres).
Toute opération sur le système de fichiers passe par ici.
"""
import os
import shutil
from pathlib import Path
from datetime import datetime
from config.settings import settings
from engine.events.bus import bus
from engine.events.types import Event, EventType


class FileManager:
    """
    Gère la structure de fichiers d'un projet.

    Structure :
    projects/{project_id}/
        notes/
            personnages/
            lieux/
            lore/
            chronologie.md
            themes.md
            story.md
        actes/
            acte_01.md
            acte_02.md
        briefs/
            chapitre_01.md
            chapitre_02.md
        chapitres/
            chapitre_01.md
            chapitre_02.md
        chapitres_versions/       ← historique des révisions
            chapitre_01_v1.md
            chapitre_01_v2.md
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.root = Path(settings.projects_dir) / project_id

    # --- Initialisation ---

    def init_project_structure(self) -> None:
        """Crée l'arborescence complète d'un nouveau projet."""
        dirs = [
            self.root / "notes" / "personnages",
            self.root / "notes" / "lieux",
            self.root / "notes" / "lore",
            self.root / "actes",
            self.root / "briefs",
            self.root / "chapitres",
            self.root / "chapitres_versions",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        # Fichiers racines du lorebook
        for filename in ["chronologie.md", "themes.md", "story.md"]:
            path = self.root / "notes" / filename
            if not path.exists():
                path.write_text(f"# {filename.replace('.md', '').capitalize()}\n\n", encoding="utf-8")

    # --- Sécurité ---

    def _safe_path(self, base: Path, relative: str) -> Path:
        """
        Vérifie qu'un chemin relatif reste bien sous `base`.
        Lève ValueError en cas de tentative de path traversal.

        - Utilise os.path.abspath (sans suivre les symlinks)
        - Normalise les séparateurs pour Windows (UNC paths inclus)
        - Refuse les chemins vides ou identiques à la base (pas de fichier cible)
        """
        if not relative or not relative.strip():
            raise ValueError("Le chemin relatif ne peut pas être vide.")

        base_abs = os.path.normcase(os.path.abspath(base))
        target_abs = os.path.normcase(os.path.abspath(os.path.join(base_abs, relative)))

        # target doit être SOUS base, pas égal à base (on veut un fichier, pas le dossier lui-même)
        if not target_abs.startswith(base_abs + os.sep):
            raise ValueError(f"Chemin invalide (traversal détecté) : {relative!r}")

        return Path(target_abs)

    # --- Lorebook ---

    def read_lorebook_file(self, relative_path: str) -> str:
        """Lit un fichier du lorebook. relative_path depuis notes/."""
        path = self._safe_path(self.root / "notes", relative_path)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_lorebook_file(self, relative_path: str, content: str) -> None:
        """Écrit un fichier du lorebook. Crée le fichier si nécessaire."""
        path = self._safe_path(self.root / "notes", relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._emit(EventType.LOREBOOK_UPDATED, {"file": relative_path})

    def list_lorebook_entities(self, entity_type: str) -> list[str]:
        """
        Retourne les noms des entités d'un type donné.
        entity_type : "personnages", "lieux", "lore"
        """
        folder = self.root / "notes" / entity_type
        if not folder.exists():
            return []
        return [f.stem for f in folder.glob("*.md")]

    def read_all_characters(self) -> dict[str, str]:
        """Retourne {nom: contenu} pour tous les personnages."""
        return self._read_all_in_folder("personnages")

    def read_all_places(self) -> dict[str, str]:
        """Retourne {nom: contenu} pour tous les lieux."""
        return self._read_all_in_folder("lieux")

    def read_character(self, name: str) -> str:
        return self.read_lorebook_file(f"personnages/{self._slugify(name)}.md")

    def write_character(self, name: str, content: str) -> None:
        self.write_lorebook_file(f"personnages/{self._slugify(name)}.md", content)

    def read_place(self, name: str) -> str:
        return self.read_lorebook_file(f"lieux/{self._slugify(name)}.md")

    def write_place(self, name: str, content: str) -> None:
        self.write_lorebook_file(f"lieux/{self._slugify(name)}.md", content)

    # --- Actes ---

    def write_act(self, act_number: int, content: str) -> None:
        path = self.root / "actes" / f"acte_{act_number:02d}.md"
        path.write_text(content, encoding="utf-8")
        self._emit(EventType.LOREBOOK_UPDATED, {"file": f"actes/acte_{act_number:02d}.md"})

    def read_act(self, act_number: int) -> str:
        path = self.root / "actes" / f"acte_{act_number:02d}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_all_acts(self) -> list[str]:
        acts = sorted((self.root / "actes").glob("acte_*.md"))
        return [a.read_text(encoding="utf-8") for a in acts]

    # --- Briefs chapitres ---

    def write_chapter_brief(self, chapter_number: int, content: str) -> str:
        path = self.root / "briefs" / f"chapitre_{chapter_number:02d}.md"
        path.write_text(content, encoding="utf-8")
        self._emit(EventType.CHAPTER_STATE_CHANGED, {
            "chapter_number": chapter_number,
            "old_state": "none",
            "new_state": "planned",
        })
        return str(path)

    def read_chapter_brief(self, chapter_number: int) -> str:
        path = self.root / "briefs" / f"chapitre_{chapter_number:02d}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # --- Chapitres rédigés ---

    def write_chapter(self, chapter_number: int, content: str) -> str:
        """Écrit le chapitre et archive la version précédente."""
        path = self.root / "chapitres" / f"chapitre_{chapter_number:02d}.md"

        # Archive la version précédente si elle existe
        if path.exists():
            self._archive_chapter(chapter_number, path.read_text(encoding="utf-8"))

        path.write_text(content, encoding="utf-8")
        self._emit(EventType.CHAPTER_STATE_CHANGED, {
            "chapter_number": chapter_number,
            "old_state": "writing",
            "new_state": "writing",
        })
        return str(path)

    def read_chapter(self, chapter_number: int) -> str:
        path = self.root / "chapitres" / f"chapitre_{chapter_number:02d}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def get_chapter_versions(self, chapter_number: int) -> list[str]:
        """Retourne les chemins de toutes les versions archivées d'un chapitre."""
        pattern = f"chapitre_{chapter_number:02d}_v*.md"
        versions = sorted((self.root / "chapitres_versions").glob(pattern))
        return [str(v) for v in versions]

    # --- Helpers internes ---

    def _archive_chapter(self, chapter_number: int, content: str) -> None:
        archive_dir = self.root / "chapitres_versions"
        existing = list(archive_dir.glob(f"chapitre_{chapter_number:02d}_v*.md"))
        version = len(existing) + 1
        archive_path = archive_dir / f"chapitre_{chapter_number:02d}_v{version}.md"
        archive_path.write_text(content, encoding="utf-8")

    def _read_all_in_folder(self, folder_name: str) -> dict[str, str]:
        folder = self.root / "notes" / folder_name
        if not folder.exists():
            return {}
        return {
            f.stem: f.read_text(encoding="utf-8")
            for f in sorted(folder.glob("*.md"))
        }

    def _emit(self, event_type: EventType, payload: dict) -> None:
        try:
            bus.emit(Event(type=event_type, project_id=self.project_id, payload=payload))
        except Exception:
            pass  # Ne jamais bloquer une écriture à cause du bus

    @staticmethod
    def _slugify(name: str) -> str:
        """
        Convertit un nom en nom de fichier valide.
        - Supprime les null bytes et caractères de contrôle
        - Remplace les caractères dangereux
        - Tronque à 100 caractères pour éviter les limites filesystem
        - Lève ValueError si le résultat est vide
        """
        if not name or not name.strip():
            raise ValueError("Le nom ne peut pas être vide.")

        # Supprime les null bytes et caractères de contrôle (< 0x20)
        cleaned = "".join(c for c in name if ord(c) >= 0x20 and c != "\x7f")

        slug = (
            cleaned.lower()
            .replace(" ", "_")
            .replace("'", "")
            .replace("/", "_")
            .replace("\\", "_")
            .replace(":", "_")
            .replace("*", "_")
            .replace("?", "_")
            .replace('"', "_")
            .replace("<", "_")
            .replace(">", "_")
            .replace("|", "_")
        )

        slug = slug[:100].strip("_")

        if not slug:
            raise ValueError(f"Le nom '{name}' produit un slug vide après nettoyage.")

        return slug
