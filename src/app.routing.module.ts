import { Routes } from '@angular/router';
import { PainelComponent } from './components/painel/painel.component';
import { AgendamentoComponent } from './components/agendamento/agendamento.component';

export const APP_ROUTES: Routes = [
  { path: '', redirectTo: 'painel', pathMatch: 'full' },
  { path: 'painel', component: PainelComponent },
  { path: 'agendar', component: AgendamentoComponent },
  { path: '**', redirectTo: 'painel' }
];
