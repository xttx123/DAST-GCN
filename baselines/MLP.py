import torch.nn.functional as F
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader
import torch.optim as optim
from torch.utils.data.sampler import SubsetRandomSampler
from sklearn.model_selection import KFold

import sklearn.metrics as results
import copy
from torch.autograd import Variable
from baselines.data import Ukbb_corr
from torch import nn

class MLP(nn.Module):
    def __init__(self, in_dim, hd1, hd2,  n_classes):
        super(MLP, self).__init__()
        self.layer1 = nn.Linear(in_dim, hd1)
        self.layer2 = nn.Linear(hd1, hd2)
        self.drop = nn.Dropout(p=0.5)

        self.classify = nn.Linear(hd2, n_classes)

    def forward(self, x):
        x = x.float().to('cuda:1')

        h1 = self.layer1(x)
        h2 = self.layer2(h1)
        hc = self.classify(h2)
        hc = self.drop(hc)
        hc = nn.functional.softmax(hc,dim=1)
        return hc

def exp_lr_scheduler(optimizer, epoch, init_lr=0.001, lr_decay_epoch=7):
    """Decay learning rate by a factor of 0.1 every lr_decay_epoch epochs."""
    lr = init_lr * (0.1**(epoch // lr_decay_epoch))

    #if epoch % lr_decay_epoch == 0:
        #print('LR is set to {}'.format(lr))

    for param_group in optimizer.param_groups:
        param_group['lr'] = lr

    return optimizer
def train_model(train_loader, val_loader, nrois, epochs):
    # Create training and testing set.

    val_loss = []
    best_val_loss = None
    best_model = None

    model = MLP(nrois, 1024, 256, 2).to('cuda:1')
    loss_func = nn.CrossEntropyLoss().to('cuda:1')
    lr = 0.00001
    optimizer = optim.Adam(model.parameters(), lr=lr)

    model.train()
    es = 10
    es_counter = 0
    print('Training....')
    epoch_losses = []
    for epoch in range(epochs):
        epoch_loss = 0
        for iter, (tc, label) in enumerate(train_loader):
            # tc = tc.to('cuda:0')
            label = Variable(label).type(torch.cuda.LongTensor).to('cuda:1')
            prediction = model(tc).to('cuda:1')
            loss = loss_func(prediction, torch.max(label, 1)[1])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.detach().item()
        epoch_loss = epoch_loss / iter
        optimizer = exp_lr_scheduler(optimizer, epoch, init_lr=lr, lr_decay_epoch=40)

        epoch_val_loss = validate_model(model, val_loader)
        val_loss.append(epoch_val_loss)

        if not best_val_loss or epoch_val_loss < best_val_loss:
            print('Saving best model ...')
            best_model = copy.deepcopy(model)
            best_val_loss = epoch_val_loss
            es_counter = 0
        if es_counter > es:
            break
        if epoch > 5:
            es_counter += 1

        print('Epoch {}, train_loss {:.3f}, val_loss {:.3f}'.format(epoch, epoch_loss, epoch_val_loss))
        epoch_losses.append(epoch_loss / (iter + 1))
    #print('Done.')
    return best_model


def validate_model(model, val_loader):
    model.eval()
    val_loss = 0
    loss_func = nn.CrossEntropyLoss().cuda()

    for iter, (tc, label) in enumerate(val_loader):
        label = Variable(label).type(torch.cuda.LongTensor)
        prediction = model(tc).cuda()
        loss = loss_func(prediction.cuda(), torch.max(label, 1)[1].cuda())
        val_loss += loss.detach().item()

    return val_loss / iter


def test_model(model, test_loader):
    model.eval()
    labels = np.empty([], dtype=int)
    predictions = np.empty([], dtype=int)
    print('Testing...')
    for iter, (tc, label) in enumerate(test_loader):
        # tc = tc.to('cuda:0')
        label = Variable(label).type(torch.cuda.LongTensor)
        prediction = model(tc).cuda()

        labels = np.append(labels, torch.argmax(label, 1).cpu().numpy())
        predictions = np.append(predictions, torch.argmax(prediction, 1).cpu().numpy())

    y_test=labels[1:]
    y_pred = predictions[1:]
    accuracy1 = results.balanced_accuracy_score(y_test, y_pred)
    sensitivity1 = results.precision_score(y_test, y_pred)
    specificity1 = results.recall_score(y_test, y_pred)

    return round(accuracy1, 3), round(sensitivity1, 3), round(specificity1, 3)




def run_kfold(df_path, atlas, epochs=100, bs=16):
    print('Preparing Data ...')
    df = pd.read_csv(df_path)
    df['Sex'].replace({'Male':0, 'Female':1},inplace=True)

    dataset = Ukbb_corr(data_info_file=df, atlas_name=atlas)
    nrois = dataset.nrois

    kf = KFold(n_splits=5,shuffle=True)
    kf.get_n_splits(dataset)
    accs = []
    senss = []
    specs = []
    k = 1

    for train_index, test_index in kf.split(dataset):

        # Creating PT data samplers and loaders:
        train_sampler = SubsetRandomSampler(train_index)
        valid_sampler = SubsetRandomSampler(test_index)
        train_loader = DataLoader(dataset, batch_size=bs, sampler=train_sampler)
        val_loader = DataLoader(dataset, batch_size=bs, sampler=valid_sampler)
        test_loader = DataLoader(dataset, batch_size=bs, sampler=valid_sampler)
        print('Training Fold : {}'.format(k))
        best_model = train_model(train_loader, val_loader, nrois, epochs)
        acc, sens, spec = test_model(best_model, test_loader)
        print("Test Accuracy for fold {} = {}".format(k, acc))
        print("Test sens for fold {} = {}".format(k, sens))
        print("Test spec for fold {} = {}".format(k, spec))
        accs.append(acc)
        senss.append(sens)
        specs.append(spec)
        k += 1
    print('-'*30)
    print("5 fold Test Accuracy: mean = {} ,std = {}".format(np.mean(accs), np.std(accs)))
    print("5 fold Test Sens: mean = {} ,std = {}".format(np.mean(senss), np.std(senss)))
    print("5 fold Test Specs: mean = {} ,std = {}".format(np.mean(specs), np.std(specs)))



if __name__ == "__main__":

    run_kfold('../csvfiles/ukbb_5000_age.csv','AAL')


