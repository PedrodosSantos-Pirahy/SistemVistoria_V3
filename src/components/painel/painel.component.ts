import { Component, ChangeDetectionStrategy, Input, output, signal, OnInit, computed, inject } from '@angular/core';
import { ApiService } from '../../services/app.service'; // Importe o serviço
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
/**
 * Interface simples para representar
 * uma vistoria pendente retornada pela API
 */
interface Inspection {
  placa: string;
  pre_ordem: string;
  transportadora: string;
  status: string;
  id: string;
  categoria_data: string;
  data?: string;
  local?: string;
  hora: string;
}


@Component({
  selector: 'app-painel',
  standalone: true,
  templateUrl: './painel.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule // ✅ ESSENCIAL PARA ngModel
  ]
})
export class PainelComponent implements OnInit {
  // Adicione ": ApiService" explicitamente aqui
  private apiService: ApiService = inject(ApiService);

  // @Input() onSelect!: (placa: string) => void;
  /**
   * Lista de vistorias pendentes exibidas no painel
   * Utiliza signal para melhor performance com OnPush
   */
  readonly inspections = signal<Inspection[]>([]);


  // PainelComponent
  readonly verTodas = output<void>();

  /**
   * Controla o estado de carregamento da tela
   */
  readonly loading = signal<boolean>(true);

  /**
   * Armazena mensagem de erro, se houver falha na API
   */
  readonly error = signal<string | null>(null);

  /**
   * Output já existente no componente.
   * NÃO foi removido para não quebrar integrações existentes.
   */
  readonly inspectionSelected = output<Inspection>();


  /* =========================================================
     ESTADOS ADICIONADOS PARA O MODAL (NÃO EXISTIAM ANTES)
     ========================================================= */

  selectedPlaca = signal<string | null>(null);
  showDecisionModal = signal<boolean>(false);
  nomeCancelamento = '';
  motivo = '';
  resposta: 'sim' | 'nao' | null = null;
  selectedInspection = signal<Inspection | null>(null);

  private irHistorico = signal(false);
  constructor(private router: Router) { }

  ngOnInit(): void {
    this.configurarFiltroUsuario();

    this.fetchInspections();

    // 🔁 força atualização a cada 30 segundos
    this.pollingInterval = window.setInterval(() => {
      this.fetchInspections();
    }, 30000); // 30s (pode baixar pra 5s)
  }

  ngOnDestroy(): void {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
    }
  }


  /**
   * Busca as vistorias pendentes no backend (Python)
   * 🔥 AGORA TAMBÉM TRAZ O STATUS
   */



async fetchInspections(force = false): Promise<void> {
    this.loading.set(true);
    this.error.set(null);

    try {
      const timestamp = new Date().getTime();
      if (force) console.log('🔄 Forçando atualização manual...');
      
      // CHAMADA VIA SERVIÇO: 
      // Substitui a URL fixa e o fetch manual pelo método do ApiService
      const response = await this.apiService.getPendencias(timestamp, force);

      if (!response.ok) {
        throw new Error(`Erro de servidor: ${response.statusText} (${response.status})`);
      }
      
      // ... restante do código (processamento do json)

      const data = await response.json();
      const pendentes = data.pendentes; // O Python envia dentro de "pendentes"

      if (!Array.isArray(pendentes)) {
        console.error('A resposta da API não é um array válido:', pendentes);
        throw new Error('Formato de dados inesperado da API.');
      }

      // --- MAPEAMENTO DO BANCO DE DADOS PARA O FRONTEND ---
      const parsedInspections: Inspection[] = pendentes
        .map((item: any) => {
          // Validação básica para não quebrar a lista
          if (!item?.id) { 
             console.warn('Item sem ID ignorado:', item);
             return null; 
          }

          return {
            id: String(item.id), // Garante que ID seja string
            placa: item.placa || 'SEM PLACA',
            
            // O Python calcula isso (Atrasado, Em Breve, Pendente...)
            status: item.status || 'Pendente', 
            
            data: item.data, // Vem como DD/MM/YYYY do Python

            hora: item.hora,
            
            // Mapeia o campo do banco (pre_ordem1) ou o que o Python enviou (pre_ordem)
            pre_ordem: item.pre_ordem || item.pre_ordem1 || '', 
            
            transportadora: item.transportadora || 'Consultar Cadastro',
            
            // Essencial para os filtros (Data Atual, Datas Futuras) funcionarem
            categoria_data: item.categoria_data?.trim(),
            
            // Se o banco não tiver local, assume Matriz para aparecer no filtro
            local: item.local 
          };
        })
        .filter(item => item !== null) as Inspection[];

      // Atualiza o sinal com a lista limpa
      this.inspections.set(parsedInspections);
      
      if (force) console.log('✅ Lista atualizada do banco de dados!');

    } catch (err) {
      console.error('Erro ao buscar dados da API:', err);
      let errorMessage = 'Não foi possível carregar as vistorias.';
      if (err instanceof Error) {
        errorMessage = `Erro de conexão com o banco/API: ${err.message}`;
      }
      this.error.set(errorMessage);
      this.inspections.set([]);
    } finally {
      this.loading.set(false);
    }
  };
  recarregarManual() {
    this.fetchInspections(true);
}

  reloadPage() {
    window.location.reload();
  }

 // 1. Definição dos Estados (Sinais)
readonly tipoFiltro = signal<'Data Atual' | 'Datas Futuras' | 'Todas as Datas'>('Data Atual');
readonly tipoLocal = signal<'Filial' | 'Matriz' | 'Qualquer'>('Qualquer');

// 2. A Mágica do Filtro (Calculado automaticamente)
readonly vistoriasFiltradas = computed(() => {
  const lista = this.inspections();
  const dataRef = this.tipoFiltro();
  const localRef = this.tipoLocal();

  return lista.filter((v: Inspection) => {
    
    // Filtra por data
    const matchData = dataRef === 'Todas as Datas' || v.categoria_data === dataRef;
    
    // Filtra por local
    const matchLocal = localRef === 'Qualquer' || v.local === localRef;

    return matchData && matchLocal;
  });
});
// DENTRO DA CLASSE PainelComponent:

  // 🔥 CONTADORES INTELIGENTES (Respeitam o Local Selecionado)
  readonly contadores = computed(() => {
    const lista = this.inspections(); // Pega tudo
    const localAtual = this.tipoLocal(); // Vê qual botão de local está marcado (ex: 'Filial')

    // 1. Primeiro filtra pelo local ativo
    const listaDoLocal = lista.filter(item => 
      localAtual === 'Qualquer' ? true : item.local === localAtual
    );

    // 2. Agora conta baseado nessa lista filtrada
    return {
      hoje: listaDoLocal.filter(i => i.categoria_data === 'Data Atual').length,
      futuras: listaDoLocal.filter(i => i.categoria_data === 'Datas Futuras').length,
      
      // Total pendente da unidade selecionada
      total: listaDoLocal.length 
    };
  });

  private pollingInterval!: number;

configurarFiltroUsuario() {
    const dados = localStorage.getItem('usuario_logado');
    if (dados) {
      const user = JSON.parse(dados);
      
      // Se o usuário tiver local definido (Matriz ou Filial), já seta o filtro
      if (user.local && (user.local === 'Matriz' || user.local === 'Filial')) {
        this.tipoLocal.set(user.local);
      } else {
        this.tipoLocal.set('Qualquer'); // Admin ou sem local vê tudo
      }
    }
  }
  selectInspection(inspection: Inspection) {
    if (this.showDecisionModal()) return;

    console.log('PAINEL EMITINDO:', inspection);
    this.inspectionSelected.emit(inspection);
  }
  irParaHistorico() {
    this.verTodas.emit();
  }

  abrirCancelamento(event: Event, inspection: Inspection) {
    event.preventDefault();
    event.stopImmediatePropagation(); // 🔑 ESSENCIAL

    this.selectedInspection.set(inspection);
    this.showDecisionModal.set(true);
  }



  fecharModal() {
    this.showDecisionModal.set(false);
    this.selectedPlaca.set(null);
    this.nomeCancelamento = '';
    this.motivo = '';

  }

async confirmarCancelamento() {
    const inspection = this.selectedInspection();

    if (!inspection || !inspection.id) {
      alert('ID da vistoria não encontrado');
      return;
    }

    const payload = {
      id: inspection.id,
      nome: this.nomeCancelamento,
      motivo: this.motivo
    };

    try {
      // SUBSTITUÍDO: Agora usa o serviço centralizado
      const response = await this.apiService.cancelarVistoria(payload);

      if (!response.ok) throw new Error('Falha ao cancelar');
      
      const result = await response.json();
      alert('✅ Cancelamento realizado!');
      this.fecharModal();
      this.fetchInspections(true);
    } catch (error) {
      alert('Erro ao cancelar vistoria');
    }
  }
}
