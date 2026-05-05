import { Component, ChangeDetectionStrategy, signal, OnInit, OnDestroy, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormComponent } from './components/form/form.component';
import { PainelComponent } from './components/painel/painel.component';
import { HistoricoComponent } from './components/historico/historico.component';
import { AgendamentoComponent } from './components/agend/agendamento.component';
import { MonitoramentoComponent } from './components/monitoramento/monitoramento.component';
import { LoginComponent } from './components/login/login.component';
import { CarregamentoComponent } from './components/carregamento/carregamento.component';
import { ApiService } from './services/app.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    FormComponent,
    PainelComponent,
    HistoricoComponent,
    AgendamentoComponent,
    MonitoramentoComponent,
    LoginComponent,
    CarregamentoComponent
  ],
  templateUrl: './app.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent implements OnInit, OnDestroy {

  private _alertInterval: any = null;

  constructor(private apiService: ApiService) {}

  isLogado = signal(false);
  temAgendSemPlaca = signal(false);
  qtdAgendSemPlaca = signal(0);
  
  // Adicionamos 'carregamento' na lista de telas permitidas
  readonly view = signal<'list' | 'form' | 'historico' | 'agendamento' | 'monitoramento' | 'carregamento' | null>(null);
  readonly selectedInspection = signal<{ placa: string; id: string } | null>(null);
  
  usuarioNome = signal('');
  usuarioCargo = signal('');

  // --- PERMISSÕES ---
  isAdmin = computed(() => ['ADM', 'TI'].includes(this.usuarioCargo()));
  isPcp = computed(() => this.usuarioCargo() === 'PCP' || this.isAdmin());
  isComercial   = computed(() => this.usuarioCargo().toUpperCase().includes('COM'));
  isExpedicao   = computed(() => this.usuarioCargo() === 'EXP' || this.isAdmin());
  isVistoriador = computed(() => this.usuarioCargo() === 'VIS' || this.isAdmin());
  isCarregamento = computed(() => this.usuarioCargo() === 'CAR' || this.isAdmin());
  isDer = computed(() => this.usuarioCargo() === 'DER');
  podeVerCarregamento = computed(() => this.isExpedicao() || this.isCarregamento() || this.isDer() || this.isPcp());

  isBalanca = computed(() => this.usuarioCargo() === 'BAL' || this.isAdmin());

  podeVerMonitoramento = computed(() =>
    this.isExpedicao() || this.isBalanca() || this.isComercial() || this.isPcp()
  );

  // Comercial pode agendar mas não vê Painel/Monitoramento/Carregamento
  podeAgendar = computed(() => this.isExpedicao() || this.isComercial());

  ngOnInit() {
    const dados = localStorage.getItem('usuario_logado');
    if (dados) {
      const user = JSON.parse(dados);
      this.isLogado.set(true);
      this.usuarioNome.set(user.nome);
      this.usuarioCargo.set(user.cargo);

      const cargo = this.usuarioCargo();

      if (cargo === 'CAR' || cargo === 'DER' || cargo === 'PCP') {
        this.view.set('carregamento');
      } else if (cargo === 'EXP' || cargo === 'COM') {
        this.view.set('monitoramento');
      } else {
        this.view.set('list');
      }

      // Alerta de agendamentos sem placa — quem pode ver monitoramento (exceto Comercial)
      if (this.podeVerMonitoramento() && !this.isComercial()) {
        this.verificarAgendSemPlaca();
        this._alertInterval = setInterval(() => this.verificarAgendSemPlaca(), 60000);
      }

    } else {
      this.isLogado.set(false);
    }
  }
  

  ngOnDestroy() {
    if (this._alertInterval) clearInterval(this._alertInterval);
  }

  verificarAgendSemPlaca() {
    this.apiService.getMonitoramento(1, 100, '', 'Qualquer', 'Todas', '', 'Todas').subscribe({
      next: (res: Record<string, any>) => {
        const dados: any[] = res['data'] ?? res['dados'] ?? res['fila_caminhoes'] ?? [];
        const semPlaca = dados.filter((item: any) => !item.placa || item.placa.trim() === '');
        this.qtdAgendSemPlaca.set(semPlaca.length);
        this.temAgendSemPlaca.set(semPlaca.length > 0);
      },
      error: () => {}
    });
  }

  logout() {
    localStorage.removeItem('usuario_logado');
    this.isLogado.set(false);
    window.location.reload();
  }

  setView(view: 'list' | 'form' | 'historico' | 'agendamento' | 'monitoramento'): void {
    if (view === 'list') this.selectedInspection.set(null);
    this.view.set(view);
  }

  onInspectionSelected(inspection: { placa: string; id: string }) {
    this.selectedInspection.set(inspection);
    this.view.set('form');
  }

  goBack(): void {
    this.selectedInspection.set(null);
    if (this.isVistoriador()) {
      this.view.set('list');
    } else if (this.isCarregamento() || this.isDer() || this.isPcp()) {
      this.view.set('carregamento');
    } else {
      this.view.set('monitoramento'); 
    }
  }
}