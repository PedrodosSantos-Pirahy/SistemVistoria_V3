import { Component, signal, computed, inject, OnInit, effect } from '@angular/core';
import { ApiService } from '../../services/app.service'; // Importe o serviço
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { DomSanitizer } from '@angular/platform-browser';

interface IntervaloOcupado {
  inicio: string;
  fim: string;
  id: string;
}

@Component({
  selector: 'app-monitoramento',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './monitoramento.component.html'
})
export class MonitoramentoComponent implements OnInit {
  
  private apiService: ApiService = inject(ApiService);
  private http: HttpClient = inject(HttpClient);
  private sanitizer: DomSanitizer = inject(DomSanitizer);

  // --- PAGINAÇÃO & DADOS ---
  paginaAtual = signal(1);
  itensPorPagina = signal(20);
  totalItens = signal(0);
  totalPaginas = signal(1);
  dadosTabela = signal<any[]>([]); 
  filtroGeral = signal('');
  loading = signal(true); 
  
  // --- DETALHES & PDF ---
  paginaDetalhesAberta = signal(false);
  itemSelecionado = signal<any>(null);
  detalhesChecklist = signal<any>(null);
  fotosDisponiveis = signal<any>(null);
  loadingDetalhes = signal(false);
  
  // 🔥 DECLARAÇÃO DO TIMESTAMP (Obrigatório)
  timestampFotos = signal(0);

  // --- NOVOS ESTADOS PARA CANCELAMENTO ---
  showCancelModal = signal(false);
  motivoCancelamento = signal('');
  usuarioNomeLogado = ''; // Variável simples para o nome fixo
  
// 🔒 CONTROLE DE ACESSO
  isTI = signal(false);
  isCarregamento = signal(false);
  isExpedicao = signal(false);
  isComercial = signal(false);

  // 📝 LOG E JUSTIFICATIVA
  modalJustificativaAberto = signal(false);
  justificativaEdicao = signal('');


pdfUrlSegura = computed(() => {
    const item = this.itemSelecionado();
    if (!item || !item.tem_pdf) return null;
    // Usa o helper do serviço para montar a URL correta
    const url = this.apiService.getPdfUrl(item.id);
    return this.sanitizer.bypassSecurityTrustResourceUrl(url);
  });

  // --- EDIÇÃO ---
  modalEdicaoAberto = signal(false);
  ocupacoesDoDia = signal<IntervaloOcupado[]>([]);

  // Validação de transportadora para agendamentos sem placa
  transpEsperada   = signal<string | null>(null);
  transpEncontrada = signal<string | null>(null);
  validacaoTransp  = signal<'ok' | 'divergencia' | 'buscando' | null>(null);

  formEdicao = signal({ 
    id: '', placa: '', data: '', hora: '', 
    duracao: 30, local: '', pre_ordens: ['', '', '', '', ''] 
  });

constructor() {
  effect(() => {
    const data = this.formEdicao().data;
    const local = this.formEdicao().local; // 🔥 NOVO: Agora vigia também a Unidade
    
    // Se o modal estiver aberto e tivermos data e local, busca a ocupação correta
    if (this.modalEdicaoAberto() && data && local) {
        this.carregarOcupacoes(data, local);
    }
  });
}
readonly tipoLocal = signal<'Qualquer' | 'Matriz' | 'Filial'>('Qualquer');
readonly tipoStatus = signal<string>('Todas');
readonly tipoDerivado = signal<'Todas' | 'Sim' | 'Nao'>('Todas');
readonly somenteMeus = signal(false);

// Variável que controla se o usuário quer limpar as ordens de propósito
  desvincularOrdens = signal(false);

  // Função que limpa as ordens quando o usuário marca a caixinha
  toggleDesvincular(marcado: boolean) {
      this.desvincularOrdens.set(marcado);
      if (marcado) {
          // Limpa todas as 5 caixinhas de ordem
          this.formEdicao.update((atual: any) => ({ ...atual, pre_ordens: ['', '', '', '', ''] }));
      }
  }

ngOnInit() {
    // 1. Tenta buscar nas duas chaves possíveis para não ter erro
    const dadosBrutos = localStorage.getItem('usuario_logado') || localStorage.getItem('user');
    
    if (dadosBrutos) {
        try {
            const user = JSON.parse(dadosBrutos);
            console.log("MEU CARGO NO SISTEMA:", user.cargo);
            this.usuarioNomeLogado = user.nome || 'Usuário TI';

            const localUser = (user.local || '').trim().toUpperCase();
            if (localUser === 'MATRIZ') {
                this.tipoLocal.set('Matriz');
            } else if (localUser === 'FILIAL') {
                this.tipoLocal.set('Filial');
            }
            // 🔍 LOG DE DEPURAÇÃO: Abra o F12 no navegador e veja o que aparece aqui
            console.log('Dados do usuário logado:', user);

            // 🔒 Verificação flexível de Cargos
            const cargo = (user.cargo || '').trim().toUpperCase();
            const depto = (user.departamento || '').trim().toUpperCase();

            // 1. TI e ADM (Veem TUDO: Carga + Edição)
            if (['TI', 'ADM'].includes(cargo) || depto === 'TI') {
                this.isTI.set(true);
            }
            // 2. Carregamento (Vê APENAS a coluna de Carga)
            else if (['CAR', 'CARREGAMENTO', 'PATIO', 'CONFERENTE'].includes(cargo)) {
                this.isCarregamento.set(true);
            }
            // 3. Expedição e Balança (Veem APENAS a coluna de Edição) → filtra Fardos
            else if (['EXP', 'EXPEDIÇÃO', 'BAL', 'BALANÇA'].includes(cargo)) {
                this.isExpedicao.set(true);
                this.tipoDerivado.set('Nao'); // Fardos
            }
            // 4. Comercial → filtra Derivados automaticamente
            else if (cargo.includes('COM')) {
                this.isComercial.set(true);
                this.tipoDerivado.set('Sim'); // Derivados
            }
        } catch (e) {
            console.error('Erro ao ler dados do localStorage', e);
        }
    }
    
    this.carregarDados();
    setInterval(() => this.carregarDados(), 45000);
}


isSearchingErp = signal(false);


// 2. Atualize o carregarDados para enviar sempre vazio no último parâmetro
carregarDados() {
    const page = this.paginaAtual();
    const limit = this.itensPorPagina();
    const busca = this.filtroGeral(); // Pega o texto da caixa única
    const local = this.tipoLocal(); 
    const status = this.tipoStatus();
    const derivado = this.tipoDerivado();
    const criador = this.somenteMeus() ? this.usuarioNomeLogado : '';

    this.loading.set(true); // Liga o loading simples

    // Passamos 'busca' no 'q' e deixamos o 'erp' (último) vazio ''
    this.apiService.getMonitoramento(page, limit, busca, local, status, '', derivado, criador).subscribe({
        next: (res) => {
            this.dadosTabela.set(res.data);
            if (res.meta) {
                this.totalItens.set(res.meta.total_items || 0);
                // 🔥 CORREÇÃO DA TABULAÇÃO: Garante que nunca seja página 0, evitando travar os botões
                this.totalPaginas.set(res.meta.total_pages || 1); 
            }
            this.loading.set(false);
        },
        error: () => this.loading.set(false)
    });
}
// No arquivo: monitoramento.component.ts

updatePlacaEdicao(valor: string) {
  let limpa = valor.toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (limpa.length > 7) limpa = limpa.slice(0, 7);
  if (limpa.length > 3) limpa = limpa.slice(0, 3) + '-' + limpa.slice(3);

  this.formEdicao.update((atual: any) => ({ ...atual, placa: limpa }));

  // Validação de transportadora: só se o agendamento era sem placa
  if (this.transpEsperada()) {
    if (limpa.length === 8) {
      this.validacaoTransp.set('buscando');
      this.apiService.consultarPlaca(limpa.replace('-', '')).subscribe({
        next: (res) => {
          this.transpEncontrada.set(res.transportadora);
          const match = res.transportadora.trim().toUpperCase() === this.transpEsperada()!.trim().toUpperCase();
          this.validacaoTransp.set(match ? 'ok' : 'divergencia');
        },
        error: () => {
          this.transpEncontrada.set(null);
          this.validacaoTransp.set('divergencia');
        }
      });
    } else {
      this.validacaoTransp.set(null);
      this.transpEncontrada.set(null);
    }
  }
}

// 2. Substitua o método updatePreOrdemEdicao por este (validando números)
updatePreOrdemEdicao(index: number, valor: string) {
  // Remove qualquer caractere que NÃO seja número
  let numeros = valor.replace(/\D/g, '');
  
  // Trava em 6 dígitos (regra do ERP)
  if (numeros.length > 6) numeros = numeros.slice(0, 6);

  this.formEdicao.update((atual: any) => {
    const novas = [...atual.pre_ordens];
    novas[index] = numeros;
    return { ...atual, pre_ordens: novas };
  });
}

// 3. (Opcional) Melhore o salvarEdicao para validar antes de enviar
salvarEdicao() {
    const dados = this.formEdicao();
    
    // Validação Placa: permite vazio (sem placa), bloqueia parcial
    if (dados.placa && dados.placa.length > 0 && dados.placa.length < 8) {
        alert('A placa deve estar completa (Ex: AAA-1234) ou deixe em branco.');
        return;
    }

    // Validação Ordens
    const temOrdemValida = dados.pre_ordens.some((o: string) => o.length > 0);
    if (!temOrdemValida) {
        alert('Informe pelo menos uma Ordem de Carregamento.');
        return;
    }

    // Código de envio real (sem os pontinhos ...)
    this.apiService.gerenciarAgendamento(this.formEdicao()).subscribe({
        next: () => {
          this.modalEdicaoAberto.set(false);
          this.carregarDados();
          alert('✅ Agendamento atualizado!');
        },
        error: (err) => alert(err.error?.error || 'Erro ao atualizar')
    });
}
// Função genérica para atualizar campos simples (placa, duração, etc)
updateEdicao(campo: string, valor: any) {
  this.formEdicao.update((atual: any) => ({ ...atual, [campo]: valor }));
}

// Função específica para trocar o local (limpa a hora para forçar nova escolha)
setLocalEdicao(local: string) {
  this.formEdicao.update((atual: any) => ({ ...atual, local: local, hora: '' }));
}


  // --- AÇÕES PRINCIPAIS ---
setSomenteMeus(valor: boolean) {
    this.somenteMeus.set(valor);
    this.paginaAtual.set(1);
    this.carregarDados();
}

setStatus(status: string) {
    this.tipoStatus.set(status);
    this.paginaAtual.set(1); // Sempre volta para a página 1 ao filtrar
    this.carregarDados();
}

  setLocal(local: 'Qualquer' | 'Matriz' | 'Filial') {
    this.tipoLocal.set(local);
    this.paginaAtual.set(1); // Volta para a página 1 ao filtrar
    this.carregarDados();
}
  // 🔥 1. ABRIR DETALHES (CORRIGIDO PARA FOTOS)
  abrirDetalhes(item: any) { 
      // Primeiro: Gera um número novo para enganar o cache
      this.timestampFotos.set(new Date().getTime());
      
      // Segundo: Seleciona o item e abre a tela
      this.itemSelecionado.set(item); 
      this.paginaDetalhesAberta.set(true); 
      
      // Terceiro: Busca os dados
      this.carregarDetalhes(item.id); 
  }
  
  fecharDetalhes() { 
      this.paginaDetalhesAberta.set(false); 
  }
  
carregarDetalhes(id: string) {
      if(!id) return;
      this.loadingDetalhes.set(true);
      // Substituído: Chamada via ApiService
      this.apiService.getDetalhesFinalizados(id).subscribe({
        next: (res) => {
            if(res.encontrado) { 
                this.detalhesChecklist.set(res);
                this.fotosDisponiveis.set(res.fotos);
            }
            this.loadingDetalhes.set(false);
        },
        error: () => this.loadingDetalhes.set(false)
      });
  }

getFotoUrl(tipo: string): string {
    const baseUrl = this.apiService.getFotoUrl(this.itemSelecionado()?.id, tipo);
    const ts = new Date().getTime(); // Gera um timestamp novo a cada milissegundo
    
    // 🚀 O SEGREDO ESTÁ AQUI:
    // 1. t=... : Quebra o cache do navegador (Chrome/Edge)
    // 2. ngsw-bypass=true : Obriga o Angular PWA a ir na rede (ignora o Service Worker)
    return `${baseUrl}?t=${ts}&ngsw-bypass=true`; 
}

imagemAmpliada = signal<string | null>(null);

// Método para abrir (substitui o abrirFotoOriginal)
verImagem(url: string) {
  if (url) {
    this.imagemAmpliada.set(url);
  }
}

// Método para fechar
fecharImagem() {
  this.imagemAmpliada.set(null);
}
  // --- EDIÇÃO ---
  aoMudarDataEdicao(novaData: string) {
    this.formEdicao.update((atual: any) => ({ ...atual, data: novaData, hora: '' }));
  }

  statusOriginalEdicao = '';

  abrirEdicao(event: Event, item: any) {
    event.stopPropagation();
    this.statusOriginalEdicao = item.vistoria_realizada;
    this.desvincularOrdens.set(false);
    const [dia, mes, ano] = item.data.split('/');
    const dataIso = `${ano}-${mes}-${dia}`;
    const ordensArray = [ item.pre_ordem1 || '', item.pre_ordem2 || '', item.pre_ordem3 || '', item.pre_ordem4 || '', item.pre_ordem5 || '' ];

    this.formEdicao.set({
        id: item.id, placa: item.placa, data: dataIso, hora: item.h_inicio,
        duracao: item.duracao || 30, local: item.local || 'Matriz', pre_ordens: ordensArray
    });

    // Se o item não tem placa, ativa validação de transportadora
    const semPlaca = !item.placa || item.placa.trim() === '';
    this.transpEsperada.set(semPlaca ? (item.transportadora || null) : null);
    this.transpEncontrada.set(null);
    this.validacaoTransp.set(null);

    this.modalEdicaoAberto.set(true);
  }

// No monitoramento.component.ts
carregarOcupacoes(data: string, local: string) {
    this.apiService.getAgendamentosDia(data, local).subscribe(dados => {
        this.ocupacoesDoDia.set(dados);
    });
}
  private timeToMinutes(time: string): number {
    const [h, m] = time.split(':').map(Number);
    return h * 60 + m;
  }

  slotsVisuais = computed(() => {
    const times = [];
    const ocupacoes = this.ocupacoesDoDia();
    const meuId = this.formEdicao().id; 
    const now = new Date();
    const isToday = this.formEdicao().data === now.toISOString().split('T')[0];
    const currentHour = now.getHours();
    const currentMinute = now.getMinutes();

    for (let h = 8; h <= 17; h++) {
      for (let m of ['00', '15', '30', '45']) {
        const slotTimeStr = `${h.toString().padStart(2, '0')}:${m}`;
        const slotMin = this.timeToMinutes(slotTimeStr);
        let isPast = false;
        if (isToday) { if (h < currentHour || (h === currentHour && Number(m) < currentMinute)) isPast = true; }

        let load = 0;
        for (const ocupacao of ocupacoes) {
           if (ocupacao.id === meuId) continue;
           const inicioMin = this.timeToMinutes(ocupacao.inicio);
           const fimMin = this.timeToMinutes(ocupacao.fim);
           if (slotMin >= inicioMin && slotMin < fimMin) load++;
        }
        times.push({ time: slotTimeStr, load: load, isPast: isPast });
      }
    }
    return times;
  });

  selecionarHorario(time: string) { this.formEdicao.update((v: any) => ({ ...v, hora: time })); }



// monitoramento.component.ts

desmarcarAgendamento() {
    // 🔥 CORREÇÃO AQUI TAMBÉM: Bloqueia cancelamento se já iniciou a vistoria
    const statusBloqueados = ['VISTORIADO', 'CARREGANDO', 'CARREGADO'];

    if (statusBloqueados.includes(this.statusOriginalEdicao)) {
        alert('🚫 Ação Bloqueada: Esta vistoria já iniciou ou foi concluída e não pode ser cancelada.');
        return;
    }

    // Se estiver pendente, abre o modal normalmente
    this.showCancelModal.set(true);
}

  fecharModalCancelamento() {
    this.showCancelModal.set(false);
    this.motivoCancelamento.set('');
  }

  confirmarCancelamentoMonitoramento() {
    const idAgendamento = this.formEdicao().id;
    const motivo = this.motivoCancelamento();

    if (!motivo) {
      alert('Por favor, informe o motivo do cancelamento.');
      return;
    }

    const payload = {
      id: idAgendamento,
      nome: this.usuarioNomeLogado, // Nome vindo do login, sem alteração
      motivo: motivo
    };

    // Usa o endpoint /cancelar que já registra nome e motivo no banco
    this.apiService.cancelarVistoria(payload).then(async (res) => {
      if (res.ok) {
        alert('✅ Agendamento cancelado com sucesso!');
        this.fecharModalCancelamento();
        this.modalEdicaoAberto.set(false); // Fecha também o modal de edição
        this.carregarDados();
      } else {
        alert('Erro ao cancelar agendamento.');
      }
    }).catch(() => alert('Erro de conexão com o servidor.'));
  }

  aoPesquisar() { this.paginaAtual.set(1); this.carregarDados(); }
  mudarPagina(p: number) { if (p >= 1 && p <= this.totalPaginas()) { this.paginaAtual.set(p); this.carregarDados(); } }

  
validarAntesDeSalvar() {
      const dados = this.formEdicao();

      // Validação de transportadora (agendamentos sem placa)
      if (this.validacaoTransp() === 'divergencia') {
        alert('Transportadora divergente. A placa informada pertence a "' + (this.transpEncontrada() || 'transportadora não encontrada') + '".\nO agendamento foi feito para: ' + this.transpEsperada());
        return;
      }
      if (this.transpEsperada() && dados.placa && this.validacaoTransp() !== 'ok') {
        alert('Aguarde a validação da transportadora ou corrija a placa.');
        return;
      }

      // Validações Básicas (Placa e Ordem): placa pode ser vazia, mas não parcial
      if (dados.placa && dados.placa.length > 0 && dados.placa.length < 8) {
          alert('A placa deve estar completa (Ex: AAA-1234) ou deixe em branco.');
          return;
      }
      const temOrdemValida = dados.pre_ordens.some((o: string) => o && o.trim().length > 0);
      if (!temOrdemValida && !this.desvincularOrdens()) {
          alert('Informe pelo menos uma Ordem de Carregamento ou marque a opção "Desvincular Ordens".');
          return;
      }

      // 🔥 CORREÇÃO AQUI: Lista dos novos status que indicam que o processo já começou/terminou
      const statusQueExigemAuditoria = ['VISTORIADO', 'CARREGANDO', 'CARREGADO'];

      // Se o status original estiver na lista acima -> Exige Auditoria
      if (statusQueExigemAuditoria.includes(this.statusOriginalEdicao)) {
          this.justificativaEdicao.set(''); 
          this.modalJustificativaAberto.set(true); // Abre o modal de log!
      } 
      // Se estiver PENDENTE ou ATRASADO -> Salva direto sem log
      else {
          this.salvarDiretoSemLog();
      }
}

  // 🚀 2. CONFIRMAÇÃO FINAL COM O LOG
  confirmarSalvarComLog() {
      const motivo = this.justificativaEdicao().trim();

      if (!motivo || motivo.length < 5) {
          alert('Por favor, descreva o motivo da alteração (mínimo 5 caracteres).');
          return;
      }

      // Prepara o payload auditado
      const payload = {
          ...this.formEdicao(),
          responsavel_edicao: this.usuarioNomeLogado, // Capturado no ngOnInit
          justificativa: motivo,
          data_log: new Date().toISOString()
      };

      this.apiService.gerenciarAgendamento(payload).subscribe({
          next: () => {
            this.modalJustificativaAberto.set(false); // Fecha auditoria
            this.modalEdicaoAberto.set(false);        // Fecha edição
            this.carregarDados();                     // Atualiza a tabela
            alert('✅ Alteração registrada e auditada com sucesso!');
          },
          error: (err) => {
              console.error(err);
              alert(err.error?.error || 'Erro ao comunicar com o servidor.');
          }
      });
  }
  salvarDiretoSemLog() {
    const payload = {
        ...this.formEdicao(),
        responsavel_edicao: this.usuarioNomeLogado,
        // Envia justificativa vazia ou fixa para indicar que foi edição normal
        justificativa: null 
    };

    this.apiService.gerenciarAgendamento(payload).subscribe({
        next: () => {
            this.modalEdicaoAberto.set(false);
            this.carregarDados();
            alert('✅ Agendamento atualizado com sucesso!');
        },
        error: (err) => alert(err.error?.error || 'Erro ao atualizar')
    });
}

  setDerivado(valor: 'Todas' | 'Sim' | 'Nao') {
      this.tipoDerivado.set(valor);
      this.paginaAtual.set(1);
      this.carregarDados();
  }

  // --- RELATÓRIO ---
  modalRelatorioAberto = signal(false);
  exportando = signal(false);
  relFiltros = signal({
    inicio: this.getDataHoje(),
    fim: this.getDataHoje(),
    status: 'Todas',
    local: 'Qualquer',
    derivado: 'Todas',
    transportadora: '',
    formato: 'excel'
  });

  getDataHoje(): string {
    return new Date().toISOString().split('T')[0];
  }

  setRelFiltro(campo: string, valor: string) {
    this.relFiltros.update((f: any) => ({ ...f, [campo]: valor }));
  }

  private _pollInterval: any = null;

  exportarRelatorio() {
    const f = this.relFiltros();
    if (!f.inicio || !f.fim) { alert('Informe as datas de início e fim.'); return; }
    this.exportando.set(true);

    this.apiService.iniciarExportacao(f).subscribe({
      next: (res) => {
        const jobId = res.job_id;
        this._pollInterval = setInterval(() => {
          this.apiService.statusRelatorio(jobId).subscribe({
            next: (job) => {
              if (job.status === 'pronto') {
                clearInterval(this._pollInterval);
                this.exportando.set(false);
                this.modalRelatorioAberto.set(false);
                const url = this.apiService.downloadRelatorioUrl(jobId);
                fetch(url).then(r => r.blob()).then(blob => {
                  const ext = this.relFiltros().formato === 'pdf' ? 'html' : 'csv';
                  const nomeArq = `Relatorio_Patio.${ext}`;
                  const blobUrl = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = blobUrl;
                  a.download = nomeArq;
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(blobUrl);
                }).catch(() => alert('Erro ao baixar o arquivo.'));
              } else if (job.status === 'erro') {
                clearInterval(this._pollInterval);
                this.exportando.set(false);
                alert('Erro ao gerar relatório: ' + (job.erro || 'Erro desconhecido'));
              }
            },
            error: () => {
              clearInterval(this._pollInterval);
              this.exportando.set(false);
              alert('Erro ao verificar status do relatório.');
            }
          });
        }, 3000);
      },
      error: () => {
        this.exportando.set(false);
        alert('Erro ao iniciar exportação.');
      }
    });
  }
}