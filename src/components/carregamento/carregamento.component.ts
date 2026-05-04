import { Component, signal, Output, EventEmitter, OnInit, inject, computed, LOCALE_ID } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms'; 
import { ApiService } from '../../services/app.service';
import { registerLocaleData } from '@angular/common';
import localePt from '@angular/common/locales/pt';
import { HttpClient } from '@angular/common/http'; // IMPORTANTE PARA A IMPRESSORA

registerLocaleData(localePt);

@Component({
  selector: 'app-carregamento',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './carregamento.component.html',
  providers: [
    { provide: LOCALE_ID, useValue: 'pt-BR' }
  ]
})
export class CarregamentoComponent implements OnInit {
  
  @Output() irParaMonitoramento = new EventEmitter<void>();
  private apiService: ApiService = inject(ApiService);
  private http: HttpClient = inject(HttpClient); // INJETADO PARA A IMPRESSORA

  loading = signal(true);

  stats = signal({
    agendadosHoje: 0,
    caminhoesLiberados: 0,
    cargasConcluidas: 0, 
    totalFardos: 0,
    totalMix: 0
  });

  resumoProdutos = signal<any[]>([]);
  filaCaminhoes = signal<any[]>([]);

  // Filtros
  filtroProduto = signal('');
  filtroUnidade = signal('');
  filtroPalete = signal('');
  tipoDerivado = signal<'Todas' | 'Sim' | 'Nao'>('Todas');
  tipoLocal = signal<'Qualquer' | 'Matriz' | 'Filial'>('Qualquer');
  dataSelecionada = signal<string>(this.getDataHoje());

  // Modal Detalhes
  paginaDetalhesAberta = signal(false);
  itemSelecionado = signal<any>(null);
  detalhesChecklist = signal<any>(null);
  fotosDisponiveis = signal<any>(null);
  loadingDetalhes = signal(false);
  timestampFotos = signal(0);
  imagemAmpliada = signal<string | null>(null);

  // --- ESTADOS DA IMPRESSORA ---
  impressorasDisponiveis = signal<string[]>([]);
  impressoraSelecionada = signal<string>('');
  imprimindo = signal(false);
  statusImpressao = signal<'Aguardando...' | 'Imprimindo...' | 'Impresso!' | 'Erro'>('Aguardando...');

  // --- PERMISSÕES DE USUÁRIO ---
  usuarioCargo = signal('');
  usuarioLocal = signal('');

  isTI = computed(() => ['TI', 'ADM'].includes(this.usuarioCargo()));
  isCarregamento = computed(() => ['CAR', 'CARREGAMENTO', 'PATIO'].includes(this.usuarioCargo()));
  isDer = computed(() => this.usuarioCargo() === 'DER');
  isCarregamentoFilial = computed(() => this.isCarregamento() && this.usuarioLocal() === 'Filial');
  isCarregamentoMatriz = computed(() => this.isCarregamento() && this.usuarioLocal() === 'Matriz');
  isDerFilial = computed(() => this.isDer() && this.usuarioLocal() === 'Filial');

  // Computados
  unidadesDisponiveis = computed(() => {
    const unids = this.resumoProdutos().map((p:any) => p.unidade);
    return [...new Set(unids)].filter(Boolean);
  });

  paletesDisponiveis = computed(() => {
    const pals = this.resumoProdutos().map((p:any) => p.palete);
    return [...new Set(pals)].filter(Boolean);
  });

  produtosFiltrados = computed(() => {
    const buscaProd = this.filtroProduto().toLowerCase();
    const buscaUnid = this.filtroUnidade().toLowerCase();
    const buscaPal = this.filtroPalete().toLowerCase();

    return this.resumoProdutos().filter((p:any) => {
      const matchProd = p.nome.toLowerCase().includes(buscaProd);
      const matchUnid = buscaUnid === '' || p.unidade.toLowerCase() === buscaUnid;
      const matchPal = buscaPal === '' || p.palete.toLowerCase() === buscaPal;
      return matchProd && matchUnid && matchPal;
    });
  });

  progressoPorcentagem = computed(() => {
    const total = this.stats().agendadosHoje;
    const feitos = this.stats().cargasConcluidas; 
    if (total === 0) return 0;
    return Math.round((feitos / total) * 100);
  });

ngOnInit() {
    const dados = localStorage.getItem('usuario_logado');
    if (dados) {
      try {
        const user = JSON.parse(dados);
        const cargo = (user.cargo || '').trim().toUpperCase();
        const local = (user.local || '').trim();

        this.usuarioCargo.set(cargo);
        this.usuarioLocal.set(local);

        // REGRA DE OURO: Trava automática por cargo
        if (this.isCarregamento()) {
           this.tipoDerivado.set('Nao'); // Fardos
           if (local === 'Filial') this.tipoLocal.set('Filial');
           else if (local === 'Matriz') this.tipoLocal.set('Matriz');
        } else if (this.isDer()) {
           this.tipoDerivado.set('Sim'); // Derivados
           if (local === 'Filial') this.tipoLocal.set('Filial');
           else if (local === 'Matriz') this.tipoLocal.set('Matriz');
        }
        // Se for TI, carrega pela última unidade dele
        else if (local === 'Matriz' || local === 'Filial') {
           this.tipoLocal.set(local);
        }
      } catch (e) { console.error('Erro ao ler usuário', e); }
    }

    this.carregarDados();
    setInterval(() => this.carregarDados(), 60000);
  }
  getDataHoje(): string {
    const tzOffset = (new Date()).getTimezoneOffset() * 60000;
    return (new Date(Date.now() - tzOffset)).toISOString().split('T')[0];
  }

setLocal(local: 'Qualquer' | 'Matriz' | 'Filial') {
    if (this.isCarregamento() || this.isDer()) return;
    this.tipoLocal.set(local);
    this.carregarDados();
  }

  setDerivado(valor: 'Todas' | 'Sim' | 'Nao') {
    if (this.isCarregamento() || this.isDer()) return;
    this.tipoDerivado.set(valor);
    this.carregarDados();
  }

  setData(novaData: string) {
    this.dataSelecionada.set(novaData);
    this.carregarDados();
  }

  carregarDados() {
    this.loading.set(true);
    this.apiService.getDashboardCarga(this.dataSelecionada(), this.tipoLocal(), this.tipoDerivado()).subscribe({
      next: (res) => {
        this.stats.set(res.stats);
        this.resumoProdutos.set(res.resumoProdutos);
        this.filaCaminhoes.set(res.filaCaminhoes);
        this.loading.set(false);
      },
      error: (err) => {
        console.error("Erro ao buscar dados do dashboard:", err);
        this.loading.set(false);
      }
    });
  }

  abrirDetalhes(item: any) {
    if (!item.id) { alert('ID não encontrado!'); return; }
    this.timestampFotos.set(new Date().getTime());
    this.itemSelecionado.set(item);
    this.paginaDetalhesAberta.set(true);
    this.carregarDetalhes(item.id);

    // IMPRESSORA: Reseta o status e busca as impressoras do Linux
    this.statusImpressao.set('Aguardando...');
    this.carregarImpressoras();
  }

  fecharDetalhes() { this.paginaDetalhesAberta.set(false); }

  carregarDetalhes(id: string) {
    this.loadingDetalhes.set(true);
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
    return `${baseUrl}?t=${this.timestampFotos()}&ngsw-bypass=true`;
  }

  verImagem(url: string) { if (url) this.imagemAmpliada.set(url); }
  fecharImagem() { this.imagemAmpliada.set(null); }
  chamarMonitoramento() { this.irParaMonitoramento.emit(); }

  // ==========================================
  // --- MÉTODOS DA IMPRESSORA ---
  // ==========================================

carregarImpressoras() {
    // Se for o pessoal da Filial, trava a impressora e nem consulta o Linux
    if (this.isCarregamentoFilial()) {
       this.impressorasDisponiveis.set(['Impressora_Carregamento_Filial']);
       this.impressoraSelecionada.set('Impressora_Carregamento_Filial');
       return;
    }

    // Se for a TI, carrega todas as impressoras
    this.http.get<string[]>(`${this.apiService.URL_HISTORICO}/impressoras`).subscribe({
      next: (imps) => {
        this.impressorasDisponiveis.set(imps);
        if (imps.length > 0) this.impressoraSelecionada.set(imps[0]);
      },
      error: () => console.error('Erro ao buscar lista de impressoras no Linux')
    });
  }

imprimirFicha() {
    const item = this.itemSelecionado();
    if (!item || !this.impressoraSelecionada()) return;

    this.imprimindo.set(true);
    this.statusImpressao.set('Imprimindo...');

    let dataFormatada = item.data;
    if (dataFormatada && dataFormatada.includes('/')) {
       const [d, m, y] = dataFormatada.split('/');
       dataFormatada = `${y}-${m}-${d}`;
    }

    // AQUI ESTÁ A CORREÇÃO: Adicionamos o id
    const payload = {
        id: item.id, // <-- Coloque esta linha!
        placa: item.placa,
        data: dataFormatada, 
        impressora: this.impressoraSelecionada()
    };

    this.http.post(`${this.apiService.URL_HISTORICO}/imprimir-direto`, payload).subscribe({
        next: (res: any) => {
            this.imprimindo.set(false);
            this.statusImpressao.set('Impresso!');

            // Marca o item como impresso localmente (card + painel sem precisar reload)
            const itemAtual = this.itemSelecionado();
            if (itemAtual) {
              const atualizado = { ...itemAtual, impresso: true };
              this.itemSelecionado.set(atualizado);
              this.filaCaminhoes.update((lista: any[]) =>
                lista.map((c: any) => c.id === itemAtual.id ? { ...c, impresso: true } : c)
              );
            }

            setTimeout(() => {
               if (this.statusImpressao() === 'Impresso!') this.statusImpressao.set('Aguardando...');
            }, 4000);
        },
        error: (err) => {
            this.imprimindo.set(false);
            this.statusImpressao.set('Erro');
            alert(err.error?.error || 'Erro ao comunicar com a impressora.');
        }
    });
  }
  
}