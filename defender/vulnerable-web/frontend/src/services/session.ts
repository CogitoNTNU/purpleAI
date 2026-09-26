const getAccessToken = () => {
  return localStorage.getItem("accessToken");
};

const setAccessToken = (token: string) => {
  localStorage.setItem("accessToken", token);
};

const removeAccessToken = () => {
  localStorage.removeItem("accessToken");
};

const getRefreshToken = () => {
  return localStorage.getItem("refreshToken");
};

const setRefreshToken = (token: string) => {
  localStorage.setItem("refreshToken", token);
};

const removeRefreshToken = () => {
  localStorage.removeItem("refreshToken");
};

const getUserName = () => {
  return localStorage.getItem("userName");
};

const setUserName = (name: string) => {
  localStorage.setItem("userName", name);
};

const removeUserName = () => {
  localStorage.removeItem("userName");
};

const getUserData = () => {
  const userData = localStorage.getItem("userData");
  return userData ? JSON.parse(userData) : null;
};

const setUserData = (userData: any) => {
  localStorage.setItem("userData", JSON.stringify(userData));
};

const removeUserData = () => {
  localStorage.removeItem("userData");
};

const getUserId = () => {
  return getUserData()?.id || null;
};

const clear = () => {
  removeAccessToken();
  removeRefreshToken();
  removeUserName();
  removeUserData();
};

export const SessionService = {
  getUserId,
  getUserName,
  setUserName,
  removeUserName,
  getUserData,
  setUserData,
  removeUserData,
  getAccessToken,
  setAccessToken,
  removeAccessToken,
  getRefreshToken,
  setRefreshToken,
  removeRefreshToken,
  clear,
};
