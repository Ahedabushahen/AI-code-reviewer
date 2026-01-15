import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import type { ReviewResult } from '../review-result/review-result';

@Component({
  selector: 'app-code-input',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './code-input.html',
  styleUrls: ['./code-input.css'],
})
export class CodeInputComponent {
  @Output() reviewed = new EventEmitter<ReviewResult>();

  language = 'typescript';
  code = '';
  loading = false;
  error: string | null = null;

  async onReview() {
    this.loading = true;
    this.error = null;

    try {
      const payload = {
        source: 'manual',
        language: this.language,
        content_type: 'code',
        content: this.code,
      };

      const res = await fetch('http://localhost:8000/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend error (${res.status}): ${text}`);
      }

      const data = (await res.json()) as ReviewResult;
      this.reviewed.emit(data);
    } catch (e: any) {
      this.error = e?.message ?? 'Unknown error';
    } finally {
      this.loading = false;
    }
  }
}
