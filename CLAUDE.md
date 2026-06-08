# Sistema de Vistorias - Pirahy | Regras do Projeto e Gestão de Memória

## Protocolo de Memória (Obrigatório)
1. **Checkpoint de Lógica:** Antes de qualquer alteração, leia os ficheiros em `memory/` para garantir que a nova implementação não quebra a lógica anterior.
2. **Atualização Pós-Tarefa:** Ao finalizar qualquer modificação, atualize imediatamente os ficheiros de memória com:
   - Resumo das alterações feitas.
   - Decisões técnicas (o "porquê").
   - Pendências geradas ou descobertas.
3. **Persistência:** Se a memória estiver ficando muito longa, resuma os pontos cruciais e limpe o que for irrelevante, mas NUNCA apague a lógica central.

## Arquitetura do Sistema
- **Backend:** Flask (`API/app.py` e `API/historico.a.py`) + PostgreSQL (DB local `DB_BUSCA`) + ERP PostgreSQL externo (tabelas `APEDIDOS`, `AEMBARITE`, `AMOVPRI`, `APED_ITEM`, `UPRODUTO`, `APALETS`, `UPESSOAS`)
- **Frontend:** Angular com signals (`signal()`, `computed()`), Tailwind CSS
- **PDF/HTML:** WeasyPrint + Jinja2 (`API/vistoria_pdf.html`) para o relatório de vistoria individual; HTML puro gerado em string para o Relatório Gerencial
- **Banco local:** Schema `vistoria` — tabelas `VAGENDAMENTO` (agendamentos) e `VRESPOSTAS` (respostas/resultados das vistorias)

## Regras de Desenvolvimento

### Banco de Dados
- **Nunca** alterar `.env` ou credenciais de banco sem perguntar.
- O campo `status` em `VRESPOSTAS` usa `'Cancelada'` (com acento), enquanto `status_patio` em `VAGENDAMENTO` usa `'CANCELADO'` (maiúsculo, sem acento) — não confundir os dois.
- `VRESPOSTAS` pode ter múltiplas linhas por `id_agend`; sempre usar `ORDER BY vistoria_fim DESC NULLS LAST LIMIT 1` ao buscar a resposta mais recente.
- `observacoes` em `VRESPOSTAS` armazena o motivo de cancelamento quando `status = 'Cancelada'`.

### Relatório Gerencial (`API/app.py` — rota `/exportar-relatorio`)
- O parâmetro `status` pode chegar como valor único (`'CANCELADO'`) ou múltiplos separados por vírgula (`'CANCELADO,VISTORIADO'`). O filtro SQL deve usar `OR` por status, nunca `= %s` direto com o valor composto.
- Para linhas com `status_patio == 'CANCELADO'`: exibir motivo do cancelamento (`row[20]` = `observacoes`) no lugar das colunas Pedido/Embarque, mas **manter** a coluna de Produtos normalmente.
- Produtos vêm do ERP via `info_erp` — se `todas_pos` (conjunto de pré-ordens numéricas) estiver vazio, a coluna mostra "Aguardando ERP...". Isso é esperado quando não há pré-ordens numéricas.
- O campo `derivado` no contexto do relatório é o **filtro** ('Sim'/'Nao'/'Todas'), não o valor por linha.

### Detalhes da Vistoria (`API/historico.a.py` — rota `/detalhes/<id>`)
- `lista_pre_ordens` vem dos índices `row[5]` a `row[9]` do SELECT principal.
- `dados_emitidos` deve ser ordenado por pré-ordem crescente após montagem completa:
  ```python
  dados_emitidos.sort(key=lambda x: (int(x["pre_ordem"]) if x["pre_ordem"].isdigit() else float('inf'), x["pre_ordem"]))
  ```
- Índices do SELECT principal: `[0]`=placa, `[2]`=hr_inicio, `[5-9]`=pre_ordens, `[10]`=status, `[14]`=observacoes, `[18]`=produto, `[20]`=observacoes (no contexto do relatório gerencial).

### Frontend (Angular)
- Componentes principais: `monitoramento` e `carregamento` — ambos têm seção de detalhes com a mesma estrutura de `dados_emitidos`.
- Alterações na tabela de detalhes devem ser replicadas nos dois componentes: `monitoramento.component.html` e `carregamento.component.html`.
- O serviço `app.service.ts` envia `status` como string única via `HttpParams` — múltiplos valores são `join(',')` no componente antes de enviar.

#### Regras de Bloqueio no Modal de Edição (`monitoramento.component.html`)
- **Campo Placa:** bloqueado (disabled + visual cinza) quando `statusOriginalEdicao` for VISTORIADO, CARREGANDO, CARREGADO ou CANCELADO, **exceto para `isTI() === true`** (cargos TI e ADM).
  - Exibe mensagem `"🔒 Placa bloqueada — vistoria já realizada. Solicite à TI para alterar."` para usuários sem permissão.
  - Motivo: usuários alteravam a placa após a vistoria para evitar refazer o processo.
- **Campo Data:** já era bloqueado para os mesmos status (comportamento anterior mantido).
- O signal `isTI` (linha 52 do `.ts`) já identifica TI/ADM e é o ponto central de controle de permissões elevadas.
- **ATENÇÃO — Armadilha de tipo:** `statusOriginalEdicao` no `.ts` é uma **string simples** (`statusOriginalEdicao = ''`), NÃO um signal. No template HTML, usar `statusOriginalEdicao` **sem parênteses**. Usar `statusOriginalEdicao()` causa erro de JS e impede o modal de renderizar completamente, quebrando a visualização para todos os cargos.

### PDF de Vistoria Individual (`API/vistoria_pdf.html`)
- `status_final == 'Sim'` → LIBERADO (verde); qualquer outro valor → REPROVADO (vermelho).
- `observacoes` contém o texto livre de observações/motivo de reprovação.
- Não exibe pedido/embarque — esses dados são do ERP e não fazem parte do checklist de inspeção.

## Pendências Conhecidas
- Verificar por que produtos às vezes demoram mais para carregar no Relatório Gerencial (provável latência na conexão ERP).
- Confirmar que o fix de múltiplos status (`OR` em vez de `=`) está funcionando após reinício do servidor Flask.
