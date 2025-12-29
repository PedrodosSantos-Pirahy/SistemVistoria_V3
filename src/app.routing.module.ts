import { Routes } from '@angular/router';
import { PainelComponent } from './components/painel/painel.component';

export const APP_ROUTES: Routes = [
  { path: '', redirectTo: 'painel', pathMatch: 'full' },
  { path: 'painel', component: PainelComponent },
  { path: '**', redirectTo: 'painel' }
];
