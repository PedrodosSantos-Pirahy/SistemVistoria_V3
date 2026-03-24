import { Component, signal, Output, EventEmitter, OnInit, inject, computed, LOCALE_ID } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms'; // 🔥 Importante para os filtros
import { ApiService } from '../../services/app.service';
import { registerLocaleData } from '@angular/common';
import localePt from '@angular/common/locales/pt';

registerLocaleData(localePt);

@Component({
  selector: 'app-carregamento',
  standalone: true,
  imports: [CommonModule, FormsModule], // 🔥 Coloque o FormsModule aqui
  templateUrl: './carregamento.component.html',
  providers: [
    { provide: LOCALE_ID, useValue: 'pt-BR' }
  ]
})
export class CarregamentoComponent implements OnInit {
  
  @Output() irParaMonitoramento = new EventEmitter<void>();
  private apiService: ApiService = inject(ApiService);

  loading = signal(true);

stats = signal({
    agendadosHoje: 0,
    caminhoesLiberados: 0,
    cargasConcluidas: 0, // 🔥 Adicione isso
    totalFardos: 0,
    totalMix: 0
  });

  resumoProdutos = signal<any[]>([]);
  filaCaminhoes = signal<any[]>([]);

  // 🔥 1. VARIÁVEIS DOS FILTROS
  filtroProduto = signal('');
  filtroUnidade = signal('');
  filtroPalete = signal('');

// Filtros de Data e Derivados
  tipoDerivado = signal<'Todas' | 'Sim' | 'Nao'>('Todas');
  dataSelecionada = signal<string>(this.getDataHoje());

  // Função auxiliar para pegar a data atual no formato YYYY-MM-DD certinho
  getDataHoje(): string {
    const tzOffset = (new Date()).getTimezoneOffset() * 60000;
    return (new Date(Date.now() - tzOffset)).toISOString().split('T')[0];
  }

  // 🔥 2. EXTRATORES DE LISTA (Para popular as caixinhas de seleção automaticamente)
  unidadesDisponiveis = computed(() => {
    const unids = this.resumoProdutos().map(p => p.unidade);
    return [...new Set(unids)].filter(Boolean); // Tira duplicados
  });

  paletesDisponiveis = computed(() => {
    const pals = this.resumoProdutos().map(p => p.palete);
    return [...new Set(pals)].filter(Boolean); // Tira duplicados
  });

  // 🔥 3. A LISTA FILTRADA QUE VAI PARA A TELA
  produtosFiltrados = computed(() => {
    const buscaProd = this.filtroProduto().toLowerCase();
    const buscaUnid = this.filtroUnidade().toLowerCase();
    const buscaPal = this.filtroPalete().toLowerCase();

    return this.resumoProdutos().filter(p => {
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
  // 🔥 FILTRO DE LOCAL (Banco de Dados)
  tipoLocal = signal<'Qualquer' | 'Matriz' | 'Filial'>('Qualquer');

  // Função para quando o usuário clicar no botão
  setLocal(local: 'Qualquer' | 'Matriz' | 'Filial') {
    this.tipoLocal.set(local);
    this.carregarDados(); // Recarrega batendo no banco de dados com o filtro novo!
  }
  // Novo: Quando clica no botão Fardo/Derivado
  setDerivado(valor: 'Todas' | 'Sim' | 'Nao') {
    this.tipoDerivado.set(valor);
    this.carregarDados();
  }

  // Novo: Quando escolhe uma data no calendário
  setData(novaData: string) {
    this.dataSelecionada.set(novaData);
    this.carregarDados();
  }

ngOnInit() {
    // 🔥 FILTRO NATIVO: Lê o banco local e já seta a unidade do usuário antes de buscar os dados
    const dados = localStorage.getItem('usuario_logado');
    if (dados) {
      try {
        const user = JSON.parse(dados);
        if (user.local === 'Matriz' || user.local === 'Filial') {
          this.tipoLocal.set(user.local);
        }
      } catch (e) {
        console.error('Erro ao ler usuário do localStorage', e);
      }
    }

    this.carregarDados();
    setInterval(() => this.carregarDados(), 60000);
  }

// Função que chama o serviço
  carregarDados() {
    // 🔥 AQUI ESTÁ A CHAVE: Enviamos a variável do botão para o Python!
    this.loading.set(true);
    this.apiService.getDashboardCarga(this.dataSelecionada(), this.tipoLocal(), this.tipoDerivado()).subscribe({
      next: (res) => {
        // Quando a resposta chegar, guardamos nos sinais!
        this.stats.set(res.stats);
        this.resumoProdutos.set(res.resumoProdutos);
        this.filaCaminhoes.set(res.filaCaminhoes);
        
        // Desliga a tela de carregamento
        this.loading.set(false);
      },
      error: (err) => {
        console.error("❌ Erro ao buscar dados do dashboard:", err);
        this.loading.set(false);
      }
    });
  }

  chamarMonitoramento() {
    this.irParaMonitoramento.emit();
  }
  // ==========================================================
  // 🔥 SINAIS E FUNÇÕES DO MODAL DE DETALHES 
  // ==========================================================
  paginaDetalhesAberta = signal(false);
  itemSelecionado = signal<any>(null);
  detalhesChecklist = signal<any>(null);
  fotosDisponiveis = signal<any>(null);
  loadingDetalhes = signal(false);
  timestampFotos = signal(0);
  imagemAmpliada = signal<string | null>(null);

  abrirDetalhes(item: any) {
    if (!item.id) { alert('ID não encontrado!'); return; }
    
    this.timestampFotos.set(new Date().getTime());
    this.itemSelecionado.set(item);
    this.paginaDetalhesAberta.set(true);
    this.carregarDetalhes(item.id);
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
    const ts = new Date().getTime();
    return `${baseUrl}?t=${ts}&ngsw-bypass=true`;
  }

  verImagem(url: string) { if (url) this.imagemAmpliada.set(url); }
  fecharImagem() { this.imagemAmpliada.set(null); }
  // ==========================================================
}