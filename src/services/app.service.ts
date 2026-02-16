import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../environments/environments'; 
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // Tipagem explícita para o TypeScript não se perder
  private http: HttpClient = inject(HttpClient);

  public readonly URL_PRINCIPAL = environment.apiUrl;      // Porta 5000
  public readonly URL_HISTORICO = environment.apiHistorico; // Porta 5002

  // ==========================================
  // API 5000 - VISTORIAS E AGENDAMENTOS
  // ==========================================

  // 🔑 Faltava este método!
  login(body: any): Observable<any> {
    return this.http.post<any>(`${this.URL_PRINCIPAL}/login`, body);
  }

  async getPendencias(timestamp: number, force = false): Promise<Response> {
    return fetch(`${this.URL_PRINCIPAL}/pendencias?t=${timestamp}${force ? '&force=true' : ''}`, {
        headers: { 'Cache-Control': 'no-cache' }
    });
  }

  getDadosCarga(placa: string): Observable<any> {
    return this.http.get<any>(`${this.URL_PRINCIPAL}/dados-carga/${placa}`);
  }

  consultarPlaca(placa: string): Observable<{ transportadora: string }> {
    return this.http.get<{ transportadora: string }>(`${this.URL_PRINCIPAL}/consultar-placa/${placa}`);
  }

  criarAgendamento(payload: any): Observable<any> {
    return this.http.post<any>(`${this.URL_PRINCIPAL}/criar-agendamento`, payload);
  }

  gerenciarAgendamento(payload: any): Observable<any> {
    return this.http.post<any>(`${this.URL_PRINCIPAL}/gerenciar-agendamento`, payload);
  }

  async enviarVistoria(formData: FormData): Promise<Response> {
    return fetch(`${this.URL_PRINCIPAL}/vistoria`, { method: 'POST', body: formData });
  }

  async cancelarVistoria(payload: any): Promise<Response> {
    return fetch(`${this.URL_PRINCIPAL}/cancelar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  // ==========================================
  // API 5002 - MONITORAMENTO E HISTÓRICO
  // ==========================================

// No arquivo app.service.ts
// No arquivo app.service.ts
getMonitoramento(page: number, limit: number, query: string, local: string = '', status: string = '') {
  // Adicionado &status=${status} ao final da URL
  return this.http.get<any>(`${this.URL_HISTORICO}/monitoramento?page=${page}&limit=${limit}&q=${query}&local=${local}&status=${status}`);
}

  // 📜 Faltava este método para a tela de Histórico!
getHistorico(page: number, limit: number, placa: string, transportadora: string, local: string = ''): Observable<any> {
    // Adicionado &local=${local} ao final da URL
    const url = `${this.URL_HISTORICO}/historico?page=${page}&limit=${limit}&placa=${placa}&transportadora=${transportadora}&local=${local}`;
    return this.http.get<any>(url);
}

// No arquivo app.service.ts
getAgendamentosDia(data: string, local: string): Observable<any[]> {
  // Adicionado &local=${local} para filtrar a ocupação por unidade
  return this.http.get<any[]>(`${this.URL_HISTORICO}/agendamentos-dia?data=${data}&local=${local}`);
}

  getDetalhesFinalizados(id: string): Observable<any> {
    return this.http.get<any>(`${this.URL_HISTORICO}/detalhes/${id}`);
  }

  verificarDuplicidade(params: string): Observable<{ duplicado: boolean }> {
    return this.http.get<{ duplicado: boolean }>(`${this.URL_HISTORICO}/verificar-duplicidade?${params}`);
  }

  // Helpers para links (HTML)
  getPdfUrl(id: string): string { return `${this.URL_HISTORICO}/pdf/${id}`; }
  getFotoUrl(id: string, tipo: string): string { return `${this.URL_HISTORICO}/foto/${id}/${tipo}`; }
}