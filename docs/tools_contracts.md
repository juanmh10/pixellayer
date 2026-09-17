# Referência de Contratos e Ferramentas MCP

Este documento define todos os contratos, esquemas Pydantic v2 e ferramentas que modelos de linguagem (LLMs) e agentes podem invocar no servidor **img-cut**.

---

## 1. Regra Fundamental de Contrato: Path-Only

Todos os inputs e outputs de imagens utilizam **caminhos de arquivos (strings)**.
- **Nenhum dado binário**: Bytes brutos e strings base64 são estritamente proibidos nas mensagens MCP.
- **Retorno padronizado de metadados**:
  ```json
  {
    "file_path": "output/imagem_nobg.png",
    "format": "png",
    "width": 1024,
    "height": 1024,
    "file_size_bytes": 524288,
    "file_size_human": "512.0 KB"
  }
  ```

---

## 2. Catálogo de Ferramentas

### 2.1. `remove_background`
Remove o fundo de uma imagem usando modelos de segmentação neural e gera canal alfa transparente.

**Parâmetros de Entrada:**
- `image_path` (string, obrigatório): Caminho para a imagem de entrada (relativo ao workspace ou absoluto).
- `model` (string, opcional, padrão: `"birefnet-general"`):
  - `birefnet-general`: Recomendado para a maioria das imagens.
  - `birefnet-portrait`: Otimizado para pessoas/retratos.
  - `birefnet-matting`: Recorte fino para cabelos, pelos e vidros.
  - `birefnet-hr`: Imagens de alta definição.
  - `rmbg-2.0`: Modelo BRIA.
  - `isnet-general`: Modelo leve para execuções rápidas.
- `output_path` (string, opcional): Caminho de saída. Se omitido, salva ao lado com sufixo `_nobg`.
- `output_format` (string, opcional, padrão: `"png"`): `"png"` ou `"webp"`.

**Resposta de Sucesso:**
```json
{
  "success": true,
  "image": { ...ImageMetadata },
  "model_used": "birefnet-general",
  "processing_time_ms": 1250,
  "original_size_bytes": 1048576,
  "reduction_percent": 50.0
}
```

### 2.2. `batch_remove_background`
Remove o fundo de múltiplas imagens em lote usando o mesmo modelo carregado na memória.

**Parâmetros de Entrada:**
- `image_paths` (lista de strings, obrigatório): Lista de caminhos para as imagens de entrada.
- `model` (string, opcional, padrão: `"birefnet-general"`): Modelo a ser utilizado.
- `output_dir` (string, opcional): Diretório onde salvar os arquivos recortados.
- `output_format` (string, opcional, padrão: `"png"`): Formato de saída (`"png"` ou `"webp"`).

---

### 2.3. `crop_image`
Recorta a imagem geometricamente ou aplica autocrop para aparar margens vazias/transparentes.

**Parâmetros de Entrada:**
- `image_path` (string, obrigatório): Caminho da imagem.
- `left` / `top` / `right` / `bottom` (inteiros, opcionais): Coordenadas da caixa delimitadora.
- `width` / `height` (inteiros, opcionais): Dimensões da área de corte.
- `autocrop` (booleano, opcional, padrão: `false`): Se ativo, remove bordas vazias automaticamente.
- `autocrop_padding` (inteiro, opcional, padrão: `0`): Margem de respiro ao redor do objeto recortado.
- `output_path` (string, opcional): Caminho de saída.

---

### 2.4. `convert_format`
Converte arquivos entre formatos com preservação de canal alfa quando suportado.

**Parâmetros de Entrada:**
- `image_path` (string, obrigatório): Caminho da imagem de entrada.
- `target_format` (string, obrigatório): `"png"`, `"webp"` ou `"jpeg"`.
- `quality` (inteiro, opcional, padrão: `90`): Nível de qualidade para formatos com perdas (1 a 100).
- `lossless` (booleano, opcional, padrão: `false`): Compressão sem perdas (WebP).
- `output_path` (string, opcional): Caminho de saída desejado.

---

### 2.3. `optimize_image`
Reduz o peso do arquivo através de compressão e remoção opcional de metadados.

**Parâmetros de Entrada:**
- `image_path` (string, obrigatório): Caminho da imagem.
- `level` (string, opcional, padrão: `"medium"`): `"lossless"`, `"light"`, `"medium"`, `"aggressive"`.
- `target_size_kb` (inteiro, opcional): Tamanho desejado em KB (ajusta qualidade iterativamente).
- `strip_metadata` (booleano, opcional, padrão: `true`): Remove EXIF e metadados.
- `output_path` (string, opcional): Caminho de destino.

---

### 2.4. `resize_image`
Redimensiona a imagem preservando proporções ou aplicando regras de escala.

**Parâmetros de Entrada:**
- `image_path` (string, obrigatório): Caminho da imagem.
- `width` (inteiro, opcional): Largura alvo em pixels.
- `height` (inteiro, opcional): Altura alvo em pixels.
- `scale_percent` (float, opcional): Escala percentual (ex: `50` para metade do tamanho).
- `mode` (string, opcional, padrão: `"fit"`): `"fit"`, `"fill"`, `"exact"`, `"percentage"`.
- `resample` (string, opcional, padrão: `"lanczos"`): `"lanczos"`, `"bicubic"`, `"bilinear"`, `"nearest"`.
- `output_path` (string, opcional): Caminho de saída.

---

### 2.5. `vectorize_image`
Converte imagem rasterizada (PNG/JPEG) para curvas vetoriais SVG via `vtracer` com filtro inteligente de anti-aliasing.

**Parâmetros de Entrada:**
- `image_path` (string, obrigatório): Caminho da imagem.
- `detail_level` (string, opcional, padrão: `"logo"`):
  - `logo` (Recomendado / Padrão): Curvas Bézier suaves, limpeza de ruído no canal alfa transparente, ideal para logotipos e ícones.
  - `medium`: Nível balanceado para ilustrações gerais.
  - `high`: Máximo de fidelidade de caminhos para texturas raster complexas.
  - `low`: Mínimo de caminhos para simplificação extrema.
- `color_mode` (string, opcional, padrão: `"color"`): `"color"` ou `"binary"`.
- `output_path` (string, opcional): Caminho do arquivo `.svg`.

**Resposta de Sucesso:**
```json
{
  "success": true,
  "svg_path": "output/imagem.svg",
  "svg_size_bytes": 124500,
  "svg_size_human": "121.5 KB",
  "original_size_bytes": 450000,
  "path_count": 1420,
  "processing_time_ms": 850
}
```

---

### 2.6. `batch_process`
Encadeia uma esteira de transformações sequenciais em uma única execução atômica para o modelo.

**Parâmetros de Entrada:**
- `image_path` (string, obrigatório): Imagem de entrada inicial.
- `steps` (lista de objetos, obrigatório): Lista ordenada de operações e parâmetros.
  Exemplo:
  ```json
  [
    {"operation": "remove_background", "params": {"model": "birefnet-general"}},
    {"operation": "resize_image", "params": {"width": 800}},
    {"operation": "convert_format", "params": {"target_format": "webp", "quality": 85}}
  ]
  ```
- `output_path` (string, opcional): Caminho final da imagem resultante.

---

### 2.7. `list_models` e `get_model_info`
Ferramentas de inspeção que **não** alocam recursos em GPU.
- `list_models`: Retorna a lista de todos os modelos, seus identificadores e se já estão carregados na memória.
- `get_model_info(model_id)`: Retorna os detalhes específicos de um modelo registrado.

---

### 2.8. `save_image`
Permite ao agente copiar/mover o arquivo processado para qualquer diretório autorizado sem ler bytes nem trafegar base64.

**Parâmetros de Entrada:**
- `source_path` (string, obrigatório): Caminho da imagem de origem (relativo ao workspace).
- `target_path` (string, obrigatório): Caminho de destino ou diretório onde salvar a imagem (relativo ao workspace).

**Resposta de Sucesso:**
```json
{
  "success": true,
  "source_path": "input/to-cut_nobg.png",
  "saved_path": "output/minha_pasta/imagem_final.png",
  "file_size_bytes": 1048576,
  "file_size_human": "1.0 MB",
  "message": "Image copied successfully without binary transfer."
}
```

---

## 3. Tratamento Estruturado de Erros

Quando ocorre uma falha em qualquer operação, o servidor nunca derruba a conexão MCP. Em vez disso, responde com estrutura padronizada:
```json
{
  "success": false,
  "error": "SECURITY_ERROR",
  "message": "Path '...' is outside of allowed workspaces. Path traversal prevented."
}
```

Principais códigos de erro:
- `FILE_NOT_FOUND`: Arquivo de entrada inexistente.
- `UNSUPPORTED_FORMAT`: Extensão não reconhecida.
- `SECURITY_ERROR`: Caminho fora do workspace configurado.
- `TIMEOUT`: Operação excedeu o tempo limite configurado (`IMGCUT_INFERENCE_TIMEOUT`).
- `MODEL_LOAD_ERROR`: Falha ao inicializar pesos da rede neural.
- `PROCESSING_ERROR`: Falha no processamento matemático da imagem.
- `UNEXPECTED_ERROR`: Exceção genérica não mapeada.

