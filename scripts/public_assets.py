"""Exact text-only frontend allowlist, shared by build, fixture and verification."""
from pathlib import Path
LOCALES=('en','vi','ja','ko','zh-Hans','fr','de','es')
BASE=('template-view.js','admin-directory-view.js','test-data-view.js','announcements.js','maintenance-banner.js','maintenance-page.js','maintenance.html','maintenance.css','notifications.js','workspace.css','workspace-view.js','workspace-ui.js','uploads.js','index.html','style.css','redesign.css','app.js','portal.js','auth.js','lifecycle.js','create-flow.js','create-journal.js','create-view.js',
      'presentation-data.js','shell-view.js','i18n.js','locale-en.js','locale-source.js','catalog-text.js','error-text.js',
      'appearance.js','architecture.js','public-preview.js','session.js','recommendations.js','product-view.js','catalog-view.js','quota-view.js','cockpit.js')
ASSETS=BASE+tuple('locales/'+code+'.json' for code in LOCALES)
def source_hashes(root):
    import hashlib
    return {name:hashlib.sha256((Path(root)/'frontend'/name).read_text(encoding='utf-8').encode('utf-8')).hexdigest() for name in ASSETS}
