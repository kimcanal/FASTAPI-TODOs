const { test, expect } = require('@playwright/test');

const username = `ui_${Date.now()}`;
const password = 'uitest1234';

test.describe.serial('To-Do List 앱 UI 테스트', () => {
  test('로그인 없이 접근하면 /login으로 리다이렉트된다', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.locator('h1')).toContainText('To-Do List');
  });

  test('회원가입하면 할 일 목록 화면으로 이동한다', async ({ page }) => {
    await page.goto('/login');
    await page.click('#toggle-btn'); // 로그인 -> 회원가입 모드로 전환
    await page.fill('#username', username);
    await page.fill('#password', password);
    await page.click('#submit-btn');

    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator('#username-info')).toHaveText(`${username}님`);
  });

  test('할 일을 추가하면 목록에 보인다', async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', username);
    await page.fill('#password', password);
    await page.click('#submit-btn');
    await expect(page).toHaveURL(/\/$/);

    await page.fill('#title', 'Playwright UI 테스트 항목');
    await page.fill('#description', '자동화된 UI 테스트');
    await page.click('#todo-form button[type="submit"]');

    const item = page.locator('#todo-list li', { hasText: 'Playwright UI 테스트 항목' });
    await expect(item).toBeVisible();
    await expect(item).toContainText('자동화된 UI 테스트');
  });

  test('완료 체크박스를 누르면 완료 필터에서 보인다', async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', username);
    await page.fill('#password', password);
    await page.click('#submit-btn');
    await expect(page).toHaveURL(/\/$/);

    const item = page.locator('#todo-list li', { hasText: 'Playwright UI 테스트 항목' });
    await item.locator('input[type="checkbox"]').check();
    await expect(item.locator('span')).toHaveClass(/done/);

    await page.click('[data-filter="completed"]');
    await expect(page.locator('#todo-list li', { hasText: 'Playwright UI 테스트 항목' })).toBeVisible();

    await page.click('[data-filter="active"]');
    await expect(page.locator('#todo-list li', { hasText: 'Playwright UI 테스트 항목' })).toHaveCount(0);
  });

  test('인라인 수정으로 제목을 바꿀 수 있다', async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', username);
    await page.fill('#password', password);
    await page.click('#submit-btn');
    await expect(page).toHaveURL(/\/$/);

    await page.click('[data-filter="all"]');
    const item = page.locator('#todo-list li', { hasText: 'Playwright UI 테스트 항목' });
    await item.getByRole('button', { name: '수정' }).click();

    // 수정 모드로 바뀌면 li.innerText가 입력값(input value)을 더 이상 포함하지 않으므로,
    // hasText로 찾은 item을 계속 쓰지 않고 편집 중인 행(li.editing)을 새로 찾는다.
    const editingRow = page.locator('#todo-list li.editing');
    await editingRow.locator('.edit-title').fill('수정된 제목');
    await editingRow.getByRole('button', { name: '저장' }).click();

    await expect(page.locator('#todo-list li', { hasText: '수정된 제목' })).toBeVisible();
  });

  test('삭제하면 목록에서 사라진다', async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', username);
    await page.fill('#password', password);
    await page.click('#submit-btn');
    await expect(page).toHaveURL(/\/$/);

    page.on('dialog', (dialog) => dialog.accept());
    const item = page.locator('#todo-list li', { hasText: '수정된 제목' });
    await item.getByRole('button', { name: '삭제' }).click();

    await expect(page.locator('#todo-list li', { hasText: '수정된 제목' })).toHaveCount(0);
  });

  test('로그아웃하면 다시 로그인 화면으로 돌아간다', async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', username);
    await page.fill('#password', password);
    await page.click('#submit-btn');
    await expect(page).toHaveURL(/\/$/);

    await page.click('#logout-btn');
    await expect(page).toHaveURL(/\/login$/);

    // 로그아웃 후 다시 / 로 직접 들어가도 로그인 화면으로 돌려보내야 한다
    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/);
  });

  test('릴리스 노트 페이지에 현재 버전이 보인다', async ({ page }) => {
    await page.goto('/release-notes');
    await expect(page.locator('h1').first()).toContainText('Release Notes');
    await expect(page.locator('.card')).toContainText('Changelog');
  });
});
