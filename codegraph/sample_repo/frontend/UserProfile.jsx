import React, { useState } from 'react';
import { formatUser } from './utils';

function UserProfile({ userId }) {
  const [user, setUser] = useState(null);

  async function loadUser() {
    const res = await fetch(`/api/users/${userId}`);
    const data = await res.json();
    setUser(formatUser(data));
  }

  return <div onClick={loadUser}>User profile placeholder</div>;
}

export default UserProfile;
