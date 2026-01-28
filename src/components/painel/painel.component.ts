import { Component, ChangeDetectionStrategy, Input, output, signal, OnInit, computed } from '@angular/core';
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
    this.fetchInspections();

    // 🔁 força atualização a cada 10 segundos
    this.pollingInterval = window.setInterval(() => {
      this.fetchInspections();
    }, 10000); // 10s (pode baixar pra 5s)
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
      // 2. Adicione &force=true se o parâmetro force for verdadeiro
      const url = `http://192.168.53.193:5000/pendencias?t=${timestamp}${force ? '&force=true' : ''}`;
      
      const response = await fetch(url, {
        method: 'GET',
        headers: {
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
      /* Metodo de produção
       const response = await fetch("/api/pendencias", {
       
      const response = await fetch("http://192.168.53.193:5000/pendencias", {
        method: 'GET' */
      });

      if (!response.ok) {
        throw new Error(`Erro de servidor: ${response.statusText} (${response.status})`);
      }

      const data = await response.json();

      /**
       * Espera-se que a API retorne:
       * pendentes: [{ placa: string, status: string }]
       */
      const pendentes = data.pendentes;

      if (!Array.isArray(pendentes)) {
        console.error('A resposta da API não é um array válido:', pendentes);
        throw new Error('Formato de dados inesperado da API.');
      }

      /**
       * Converte os objetos da API
       * mantendo placa + status
       */
      const parsedInspections: Inspection[] = pendentes

        .map((item: any) => {
          if (!item?.placa || !item?.status || !item?.id) {
            console.warn('Item inválido ignorado:', item);
            return null;
          }

          return {
            placa: item.placa,
            status: item.status,
            id: item.id,
            data: item.data,
            pre_ordem: item.pre_ordem,
            transportadora: item.transportadora,
            categoria_data: item.categoria_data?.trim()
          };
        })
        .filter(item => item !== null) as Inspection[];



      // Atualiza o estado do painel
      this.inspections.set(parsedInspections);
      if (force) {
        // Se quiser algo mais sutil, use um Toast, mas por enquanto:
        console.log('✅ Lista atualizada manualmente com sucesso!');
      }
    } catch (err) {
      console.error('Erro ao buscar dados da API:', err);

      let errorMessage = 'Não foi possível carregar as vistorias.';
      if (err instanceof Error) {
        errorMessage = `Não foi possível conectar a API na rede. Detalhes: ${err.message}`;
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

  tipoFiltro = signal<
    'Data Atual' | 'Datas Anteriores' | 'Datas Futuras' | 'Todas as Datas'>('Data Atual');


  get vistoriasFiltradas(): Inspection[] {
    const lista = this.inspections();
    const filtro = this.tipoFiltro();

    if (filtro === 'Todas as Datas') {
      return lista;
    }

    return lista.filter(v => v.categoria_data === filtro);
  }



  tituloFiltro = computed(() => {
    switch (this.tipoFiltro()) {
      case 'Data Atual': return 'Hoje';
      case 'Datas Anteriores': return 'Datas Anteriores';
      case 'Datas Futuras': return 'Datas Futuras';
      default: return '';
    }
  });



  private pollingInterval!: number;


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
      id: inspection.id, // 🔑 VEM DO JSON DE PENDENCIAS
      nome: this.nomeCancelamento,
      motivo: this.motivo
    };

    console.log('ENVIANDO CANCELAMENTO:', payload);

    const response = await fetch('http://192.168.53.193:5000/cancelar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await response.json();

    if (!response.ok) {
      alert(result.error || 'Erro ao cancelar');
      return;
    }


    this.fecharModal();



  };
}
