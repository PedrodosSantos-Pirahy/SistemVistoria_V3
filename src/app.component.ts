import { Component, ChangeDetectionStrategy, signal, OnInit, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormComponent } from './components/form/form.component';
import { PainelComponent } from './components/painel/painel.component';
import { HistoricoComponent } from './components/historico/historico.component';
import { AgendamentoComponent } from './components/agend/agendamento.component';
import { MonitoramentoComponent } from './components/monitoramento/monitoramento.component';
import { LoginComponent } from './components/login/login.component';
import { CarregamentoComponent } from './components/carregamento/carregamento.component';

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
export class AppComponent implements OnInit {

  isLogado = signal(false);
  
  // Adicionamos 'carregamento' na lista de telas permitidas
  readonly view = signal<'list' | 'form' | 'historico' | 'agendamento' | 'monitoramento' | 'carregamento' | null>(null);
  readonly selectedInspection = signal<{ placa: string; id: string } | null>(null);
  
  usuarioNome = signal('');
  usuarioCargo = signal('');

  // --- PERMISSÕES ---
  isAdmin = computed(() => ['ADM', 'TI'].includes(this.usuarioCargo()));
  
  isExpedicao = computed(() => this.usuarioCargo() === 'EXP' || this.isAdmin());
  isVistoriador = computed(() => this.usuarioCargo() === 'VIS' || this.isAdmin());
  isCarregamento = computed(() => this.usuarioCargo() === 'CAR' || this.isAdmin());
  podeVerCarregamento = computed(() => this.isExpedicao() || this.isCarregamento());
  
  // ✨ NOVO: Permissão para Balança (BAL)
  isBalanca = computed(() => this.usuarioCargo() === 'BAL' || this.isAdmin());

  // 🔥 ATUALIZADO: Adicionado isBalanca() na regra de quem vê o monitoramento
  podeVerMonitoramento = computed(() => 
    this.isExpedicao() || this.isCarregamento() || this.isBalanca()
  );

  ngOnInit() {
    const dados = localStorage.getItem('usuario_logado');
    if (dados) {
      const user = JSON.parse(dados);
      this.isLogado.set(true);
      this.usuarioNome.set(user.nome);
      this.usuarioCargo.set(user.cargo);

      const cargo = this.usuarioCargo();
      
      // 🔥 ATUALIZADO: Regras de redirecionamento no Login
      if (cargo === 'CAR') {
        this.view.set('carregamento'); // Carregamento cai DIRETRO no Dashboard
      } else if (cargo === 'EXP' || cargo === 'BAL') {
        this.view.set('monitoramento'); // Expedição e Balança caem no Monitoramento
      } else {
        this.view.set('list'); // Vistoriadores e ADMs começam no Painel
      }

    } else {
      this.isLogado.set(false);
    }
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
    } else if (this.isCarregamento()) {
      this.view.set('carregamento'); // 🔥 Volta para o painel de carga
    } else {
      this.view.set('monitoramento'); 
    }
  }
}