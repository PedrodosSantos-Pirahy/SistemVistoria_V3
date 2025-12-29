import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { ReactiveFormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';

import { AppComponent } from './app.component';
import { PainelComponent } from './components/painel/painel.component';
import { APP_ROUTES } from './app.routing.module';

@NgModule({
  declarations: [
    AppComponent,
    PainelComponent,

  ],
  imports: [
    BrowserModule,
    ReactiveFormsModule,
    RouterModule.forRoot(APP_ROUTES)
  ],
  bootstrap: [AppComponent]
})
export class AppModule {}
