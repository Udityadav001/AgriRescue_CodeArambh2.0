
const loginPanel = document.getElementById("loginPanel");
const dashboard = document.getElementById("dashboard");
const loginForm = document.getElementById("loginForm");
const loginMessage = document.getElementById("loginMessage");
const dashboardMessage = document.getElementById("dashboardMessage");
const logoutBtn = document.getElementById("logoutBtn");

let allUsers = [];
let allProducts = [];
let allOrders = [];
let loading = false;

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    credentials: "same-origin",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers
    }
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status}).`);
  }
  return data;
}

function addCell(row, value) {
  const td = document.createElement("td");
  td.textContent = value == null ? "" : String(value);
  row.appendChild(td);
  return td;
}

function renderTable(tableId, rows, columns, emptyText) {
  const tbody = document.getElementById(tableId);
  tbody.replaceChildren();

  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = addCell(tr, emptyText);
    td.colSpan = columns.length;
    td.className = "empty";
    tbody.appendChild(tr);
    return;
  }

  rows.forEach(item => {
    const tr = document.createElement("tr");

    columns.forEach(column => {
      const td = addCell(tr, item[column.key]);

      if (column.roleBadge) {
        const role = String(item[column.key] || "").toLowerCase();
        const badge = document.createElement("span");
        badge.className = "role-label";
        if (role === "farmer" || role === "buyer") {
          badge.classList.add(`role-${role}`);
        }
        badge.textContent = role || "Unknown";
        td.replaceChildren(badge);
      }

      if (column.money && item[column.key] != null) {
        td.textContent = `₹${Number(item[column.key]).toLocaleString("en-IN", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2
        })}`;
      }
    });

    tbody.appendChild(tr);
  });
}

function renderUsers() {
  const search = document.getElementById("userSearch").value.trim().toLowerCase();
  const role = document.getElementById("roleFilter").value;

  const rows = allUsers.filter(user => {
    const text = [user.name, user.phone, user.address, user.role]
      .join(" ").toLowerCase();
    return text.includes(search) && (role === "all" || user.role === role);
  });

  document.getElementById("usersTotal").textContent = `${rows.length} users`;
  renderTable("usersTable", rows, [
    { key: "id" },
    { key: "name" },
    { key: "phone" },
    { key: "role", roleBadge: true },
    { key: "address" }
  ], "No matching users found.");
}

function renderProducts() {
  const search = document.getElementById("productSearch").value.trim().toLowerCase();

  const rows = allProducts.filter(product =>
    [product.name, product.farmer_name, product.farmer_phone, product.location]
      .join(" ").toLowerCase().includes(search)
  );

  document.getElementById("productsTotal").textContent = `${rows.length} products`;
  renderTable("productsTable", rows, [
    { key: "id" },
    { key: "name" },
    { key: "farmer_name" },
    { key: "farmer_phone" },
    { key: "price", money: true },
    { key: "quantity" },
    { key: "location" }
  ], "No matching products found.");
}

function renderOrders() {
  const search = document.getElementById("orderSearch").value.trim().toLowerCase();

  const rows = allOrders.filter(order =>
    [order.id, order.product_name, order.buyer_name, order.farmer_name, order.status]
      .join(" ").toLowerCase().includes(search)
  );

  document.getElementById("ordersTotal").textContent = `${rows.length} orders`;
  renderTable("ordersTable", rows, [
    { key: "id" },
    { key: "product_name" },
    { key: "buyer_name" },
    { key: "farmer_name" },
    { key: "quantity" },
    { key: "total", money: true },
    { key: "status" }
  ], "No matching orders found.");

  renderTable("recentOrdersTable", allOrders.slice(0, 5), [
    { key: "id" },
    { key: "product_name" },
    { key: "buyer_name" },
    { key: "farmer_name" },
    { key: "total", money: true },
    { key: "status" }
  ], "No orders have been placed yet.");
}

async function loadDashboard() {
  if (loading) return;
  loading = true;
  dashboardMessage.textContent = "";

  try {
    const [summary, users, products, orders] = await Promise.all([
      api("/api/admin/summary"),
      api("/api/admin/users"),
      api("/api/admin/products"),
      api("/api/admin/orders")
    ]);

    document.getElementById("farmersCount").textContent = summary.farmers;
    document.getElementById("buyersCount").textContent = summary.buyers;
    document.getElementById("productsCount").textContent = summary.products;
    document.getElementById("ordersCount").textContent = summary.orders;

    allUsers = users;
    allProducts = products;
    allOrders = orders;

    renderUsers();
    renderProducts();
    renderOrders();
  } catch (error) {
    dashboardMessage.textContent = error.message;
    throw error;
  } finally {
    loading = false;
  }
}

async function openDashboard() {
  try {
    await loadDashboard();
    loginPanel.classList.add("hidden");
    dashboard.classList.remove("hidden");
    dashboardMessage.textContent = "";
  } catch (error) {
    dashboard.classList.add("hidden");
    loginPanel.classList.remove("hidden");
    loginMessage.textContent = error.message;
  }
}

loginForm.addEventListener("submit", async event => {
  event.preventDefault();
  loginMessage.textContent = "";

  const button = loginForm.querySelector("button[type='submit']");
  button.disabled = true;
  button.textContent = "Signing in...";

  try {
    await api("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({
        phone: document.getElementById("phone").value.trim(),
        password: document.getElementById("password").value
      })
    });

    await openDashboard();
  } catch (error) {
    loginMessage.textContent = error.message;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Sign in to dashboard <span>→</span>';
  }
});

function navigateTo(sectionId) {
  const section = document.getElementById(sectionId);
  if (!section) return;

  document.querySelectorAll(".dashboard-section").forEach(item => {
    item.classList.toggle("hidden", item !== section);
  });

  document.querySelectorAll(".nav-link").forEach(item => {
    item.classList.toggle("active", item.dataset.tab === sectionId);
  });

  const labels = {
    overviewSection: "Overview",
    usersSection: "Farmers & Buyers",
    productsSection: "Products",
    ordersSection: "Orders"
  };

  document.getElementById("pageLabel").textContent = labels[sectionId] || "Dashboard";
  document.getElementById("sidebar").classList.remove("open");
}

document.querySelectorAll("[data-tab]").forEach(button => {
  button.addEventListener("click", () => navigateTo(button.dataset.tab));
});

document.getElementById("userSearch").addEventListener("input", renderUsers);
document.getElementById("roleFilter").addEventListener("change", renderUsers);
document.getElementById("productSearch").addEventListener("input", renderProducts);
document.getElementById("orderSearch").addEventListener("input", renderOrders);

document.getElementById("refreshBtn").addEventListener("click", async () => {
  const button = document.getElementById("refreshBtn");
  button.disabled = true;
  button.textContent = "Loading...";

  try {
    await loadDashboard();
  } catch (_) {
    // The message is displayed in the dashboard.
  } finally {
    button.disabled = false;
    button.textContent = "↻ Refresh";
  }
});

document.getElementById("menuBtn").addEventListener("click", () => {
  document.getElementById("sidebar").classList.toggle("open");
});

logoutBtn.addEventListener("click", async () => {
  logoutBtn.disabled = true;

  try {
    await api("/api/admin/logout", { method: "POST" });
    dashboard.classList.add("hidden");
    loginPanel.classList.remove("hidden");
    loginForm.reset();
    loginMessage.textContent = "";
    navigateTo("overviewSection");
  } catch (error) {
    dashboardMessage.textContent = error.message;
  } finally {
    logoutBtn.disabled = false;
  }
});

// On page load, the backend checks whether an admin session exists.
openDashboard();
