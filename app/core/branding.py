import json
import os
from pathlib import Path

LOCAL_FILE = Path(__file__).resolve().parents[2] / 'brand.local.json'

DEFAULTS = {
    'name': 'Hospeda',
    'tagline': 'Gestão de hospedagem',
    'location': '',
    'logo': 'img/logo.svg',
}

def load_brand():
    """Identidade visual exibida nas telas.

    Os padrões são genéricos para que o repositório possa ser público. Cada
    instalação define a própria marca em brand.local.json (fora do git) ou por
    variáveis de ambiente BRAND_NAME, BRAND_TAGLINE, BRAND_LOCATION e
    BRAND_LOGO, que têm prioridade. Logos próprios ficam em static/img/brand/.
    """
    brand = dict(DEFAULTS)
    if LOCAL_FILE.exists():
        brand.update(json.loads(LOCAL_FILE.read_text(encoding='utf-8')))
    for key in DEFAULTS:
        env_value = os.environ.get(f'BRAND_{key.upper()}')
        if env_value:
            brand[key] = env_value
    brand['subtitle'] = f"{brand['tagline']} • {brand['location']}" if brand['location'] else brand['tagline']
    return brand
