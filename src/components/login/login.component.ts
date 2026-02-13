import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.component.html' // Use seu HTML que você já mandou
})
export class LoginComponent {
  usuario = '';
  senha = '';
  loading = signal(false);
  erro = signal('');

  constructor(private http: HttpClient) {}

  entrar() {
    this.loading.set(true);
    this.erro.set('');
    
    const body = { usuario: this.usuario, senha: this.senha };

    this.http.post<any>('http://192.168.53.193:5000/login', body)
      .subscribe({
        next: (res: any) => {
          // 1. Salva o usuário
          localStorage.setItem('usuario_logado', JSON.stringify(res.user));
          // 2. Recarrega a página para o AppComponent ler o localStorage e abrir o sistema
          window.location.reload();
        },
        error: (err: any) => {
          this.loading.set(false);
          this.erro.set(err.error?.error || 'Erro ao conectar.');
        }
      });
  }
}