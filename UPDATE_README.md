# FranXX Macro — Sistema de Auto-Update

## Como funciona

1. A app verifica `UPDATE_CHECK_URL` (definido em `main.py`) 3 segundos após abrir.
2. Se a versão remota for maior que `APP_VERSION`, aparece um popup de atualização.
3. O utilizador clica **"Instalar Atualização"** — faz download do novo `.exe`.
4. Um batch script substitui o `.exe` antigo pelo novo e reinicia a app automaticamente.

O botão **"🔄 Verificar Updates"** na sidebar permite verificar manualmente a qualquer momento.

---

## Setup (1 vez)

### 1. Cria o `version.json` num URL público

Exemplo com GitHub (recomendado):
- Faz upload do `version.json` para o teu repositório em `main` branch.
- URL raw: `https://raw.githubusercontent.com/SEU_USER/FranxxMacro/main/version.json`

Exemplo com Pastebin / gist — qualquer URL que sirva JSON raw funciona.

### 2. Edita `main.py`

Procura estas duas linhas e ajusta:

```python
APP_VERSION     = "4.0.0"          # ← versão deste executável
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/SEU_USER/FranxxMacro/main/version.json"
```

### 3. Formato do `version.json`

```json
{
  "version": "4.1.0",
  "download_url": "https://github.com/.../releases/download/v4.1.0/FranxxMacro.exe",
  "changelog": "- Fix bug X\n- Melhorou Y"
}
```

---

## Lançar uma nova versão

1. Compila o novo `.exe` com `build.bat`.
2. Faz upload do `.exe` para GitHub Releases (ou qualquer host de ficheiros).
3. Atualiza o `version.json` com a nova versão e o link direto para o `.exe`.
4. Push do `version.json` — todos os utilizadores verão o popup na próxima abertura.

---

## Notas

- Em modo de desenvolvimento (`python main.py`), o update **não substitui ficheiros** — mostra apenas onde o novo `.exe` foi guardado.
- Se o utilizador não tiver internet, o check falha silenciosamente.
- O batch de substituição apaga-se a si próprio após a instalação.
