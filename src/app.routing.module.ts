import { Routes } from '@angular/router';

export const APP_ROUTES: Routes = [
  // Deixe vazio ou apenas com um redirecionamento de segurança
  // Isso garante que a URL fique sempre limpa (ex: 192.168.x.x:4200/#/)
  { path: '**', redirectTo: '' }
];