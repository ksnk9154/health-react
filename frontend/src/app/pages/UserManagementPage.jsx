import { useEffect, useMemo, useState } from 'react';
import GlassCard from '../components/GlassCard';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Avatar, AvatarFallback } from '../components/ui/avatar';
import { Search, Plus, Edit, Trash2, UserPlus } from 'lucide-react';
import { toast } from 'sonner';
import { useLanguage } from '../i18n/LanguageContext';

import { usersService } from '../services/api';

const UserManagementPage = () => {
  const { t } = useLanguage();
  const [searchTerm, setSearchTerm] = useState('');
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);

  // Backend model: { id, username, role }
  const [users, setUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const [formData, setFormData] = useState({
    username: '',
    role: 'User',
    password: '',
  });

  const loadUsers = async () => {
    setIsLoading(true);
    try {
      const resp = await usersService.getAll();
      // Backend returns: [{id, username, role}]
      const mapped = (resp || []).map((u) => ({
        id: u.id,
        username: u.username,
        name: u.username, // UI expects name/email/status/lastLogin; backend doesn't provide them.
        email: '',
        role: u.role,
        status: 'active',
        lastLogin: '',
      }));
      setUsers(mapped);
    } catch (e) {
      console.error('Failed to load users', e);
      toast.error(t('userMgmt.loadFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);



  const handleEdit = (user) => {
    // Populate form for editing
    setSelectedUser(user);
    setFormData({
      name: user.name,
      username: user.username,
      email: user.email,
      role: user.role,
      status: user.status,
      password: '',
    });
    setIsDialogOpen(true);
  };

const handleDelete = async (id) => {
    if (!window.confirm(t('userMgmt.deleteConfirm'))) return;
    try {
      await usersService.delete(id);
      toast.success(t('userMgmt.deleted'));
      await loadUsers();
    } catch (err) {
      console.error('Delete user failed', err);
      toast.error(err.response?.data?.detail || t('userMgmt.deleteFailed'));
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      if (selectedUser) {
        // PUT /admin/users/{id} expects: { username, role }
        const payload = {
          username: (formData.username || '').trim(),
          role:
            formData.role === 'admin'
              ? 'Admin'
              : formData.role === 'staff'
                ? 'Staff'
                : 'User',
        };
        await usersService.update(selectedUser.id, payload);
        toast.success(t('userMgmt.updated'));

        await loadUsers();
        handleCloseDialog();
        return;
      }

      // POST /admin/users expects: { username, password, role }
      const payload = {
        username: (formData.username || '').trim(),
        password: formData.password,
        role:
          formData.role === 'admin'
            ? 'Admin'
            : formData.role === 'staff'
              ? 'Staff'
              : formData.role === 'doctor' || formData.role === 'nurse'
                ? 'User'
                : formData.role,
      };

      await usersService.create(payload);
      toast.success(t('userMgmt.created'));

      // Refresh from backend so user persists after F5
      await loadUsers();
      handleCloseDialog();
    } catch (err) {
      console.error('User save failed', err);
      toast.error(err.response?.data?.detail || t('userMgmt.createFailed'));
    }
  };


  const handleCloseDialog = () => {
    setIsDialogOpen(false);
    setSelectedUser(null);
    setFormData({
      username: '',
      name: '',
      email: '',
      role: 'staff',
      status: 'active',
      password: ''
    });
  };

  const getInitials = (name) => {
    return name
      .split(' ')
      .map(word => word[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  const getRoleBadgeColor = (role) => {
    const colors = {
      admin: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
      doctor: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
      nurse: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
      staff: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400'
    };
    return colors[role] || colors.staff;
  };

  const filteredUsers = users.filter(user =>
    user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.email.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{t('userMgmt.title')}</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            {t('userMgmt.subtitle')}
          </p>
        </div>
        <Button
          onClick={() => setIsDialogOpen(true)}
          className="bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white shadow-lg"
        >
          <UserPlus className="w-4 h-4 mr-2" />
          {t('userMgmt.addUser')}
        </Button>
      </div>

      {/* Search Bar */}
      <GlassCard className="p-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <Input
            placeholder={t('userMgmt.searchPlaceholder')}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10 backdrop-blur-sm bg-white/50 dark:bg-gray-800/50"
          />
        </div>
      </GlassCard>

      {/* Users Table */}
      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-gray-200/50 dark:border-gray-700/50">
                <TableHead>{t('userMgmt.user')}</TableHead>
                <TableHead>{t('userMgmt.username')}</TableHead>
                <TableHead>{t('userMgmt.email')}</TableHead>
                <TableHead>{t('userMgmt.role')}</TableHead>
                <TableHead>{t('userMgmt.status')}</TableHead>
                <TableHead>{t('userMgmt.lastLogin')}</TableHead>
                <TableHead className="text-right">{t('userMgmt.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredUsers.map((user) => (
                <TableRow key={user.id} className="border-gray-200/50 dark:border-gray-700/50">
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <Avatar>
                        <AvatarFallback className="bg-gradient-to-br from-blue-500 to-indigo-600 text-white">
                          {getInitials(user.name)}
                        </AvatarFallback>
                      </Avatar>
                      <span className="font-medium">{user.name}</span>
                    </div>
                  </TableCell>
                  <TableCell>{user.username}</TableCell>
                  <TableCell>{user.email}</TableCell>
                  <TableCell>
                    <Badge className={getRoleBadgeColor(user.role)}>
                      {user.role}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={user.status === 'active' ? 'default' : 'secondary'}
                      className={
                        user.status === 'active'
                          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                          : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400'
                      }
                    >
                      {user.status === 'active' ? t('userMgmt.statusActive') : t('userMgmt.statusInactive')}
                    </Badge>
                  </TableCell>
                  <TableCell>{new Date(user.lastLogin).toLocaleDateString()}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleEdit(user)}
                        className="h-8 w-8 p-0"
                      >
                        <Edit className="w-4 h-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDelete(user.id)}
                        className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
                        disabled={user.role === 'admin'}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </GlassCard>

      {/* Add/Edit Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="backdrop-blur-md bg-white/95 dark:bg-gray-800/95 sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>
              {selectedUser ? t('userMgmt.editUser') : t('userMgmt.addNewUser')}
            </DialogTitle>
            <DialogDescription>
              {selectedUser
                ? t('userMgmt.editUserDesc')
                : t('userMgmt.addUserDesc')}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit}>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="name">{t('userMgmt.fullName')}</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="username">{t('userMgmt.username')}</Label>
                <Input
                  id="username"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">{t('userMgmt.email')}</Label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="role">{t('userMgmt.role')}</Label>
                  <select
                    id="role"
                    value={formData.role}
                    onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                    className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  >
                    <option value="staff">{t('userMgmt.roleStaff')}</option>
                    <option value="nurse">{t('userMgmt.roleNurse')}</option>
                    <option value="doctor">{t('userMgmt.roleDoctor')}</option>
                    <option value="admin">{t('userMgmt.roleAdmin')}</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="status">{t('userMgmt.status')}</Label>
                  <select
                    id="status"
                    value={formData.status}
                    onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                    className="w-full px-3 py-2 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  >
                    <option value="active">{t('userMgmt.statusActive')}</option>
                    <option value="inactive">{t('userMgmt.statusInactive')}</option>
                  </select>
                </div>
              </div>
              {!selectedUser && (
                <div className="space-y-2">
                  <Label htmlFor="password">{t('userMgmt.password')}</Label>
                  <Input
                    id="password"
                    type="password"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    required={!selectedUser}
                    placeholder={selectedUser ? t('userMgmt.passwordPlaceholder') : ''}
                  />
                </div>
              )}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleCloseDialog}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" className="bg-gradient-to-r from-blue-500 to-indigo-600 text-white">
                {selectedUser ? t('common.update') : t('common.create')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default UserManagementPage;