import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-code-input',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './code-input.html',
  styleUrls: ['./code-input.css'],
})
export class CodeInputComponent {
  language = 'typescript';
  code = '';
  loading = false;

  lastPayload: any = null;

  async onReview() {
    this.loading = true;

    this.lastPayload = {
      source: 'manual',
      language: this.language,
      content_type: 'code',
      content: this.code,
    };

    await new Promise((r) => setTimeout(r, 300));
    this.loading = false;
  }
}
