import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ReviewResult } from './review-result';

describe('ReviewResult', () => {
  let component: ReviewResult;
  let fixture: ComponentFixture<ReviewResult>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ReviewResult]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ReviewResult);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
