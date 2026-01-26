// offline-storage.service.ts
import { Injectable } from '@angular/core';
import { openDB } from 'idb';

export interface VistoriaDraft {
  vistoriaId: string | null;
  placa: string | null;
  stepAtual: number;
  payload: any;
  atualizadoEm: string;
  sincronizado: boolean;
}

@Injectable({ providedIn: 'root' })
export class OfflineStorageService {

  private dbPromise = openDB('vistoria-db', 1, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('drafts')) {
        db.createObjectStore('drafts', {
          keyPath: 'vistoriaId'
        });
      }
    }
  });

  async salvarResposta(draft: VistoriaDraft) {
    const db = await this.dbPromise;
    await db.put('drafts', draft);
  }

  async buscarPorVistoriaId(id: string) {
    const db = await this.dbPromise;
    return db.get('drafts', id);
  }

  async deletarPorVistoriaId(id: string) {
    const db = await this.dbPromise;
    await db.delete('drafts', id);
  }
}
