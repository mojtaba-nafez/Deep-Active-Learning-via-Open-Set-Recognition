import torch
from torchvision import datasets, transforms,models
import torch.utils.data.sampler  as sampler
import torch.utils.data as data
import torch.nn as nn

import numpy as np
import argparse
import random
import os

from custom_datasets import *
import model
import vgg
from solver import Solver
from utils import *
import arguments_yaml
import pickle
import visdom
import shutil
import yaml
from easydict import EasyDict
from initialization import WeightInit
from lib.Utility.utils import save_checkpoint
import visualization
from torchsummary import summary
import GPUtil as GPU
# Custom library
torch.cuda.set_device(1)

# Execution flags
d={10: [49, 33, 71, 23, 60],
 0: [72, 4, 95, 30, 55],
 4: [51, 0, 53, 57, 83],
 2: [92, 70, 82, 54, 62],
 11: [15, 21, 19, 31, 38],
 7: [14, 24, 6, 7, 18],
 12: [75, 63, 66, 64, 34],
 19: [81, 69, 41, 89, 85],
 5: [40, 39, 22, 87, 86],
 8: [43, 97, 42, 3, 88],
 15: [29, 93, 27, 78, 44],
 3: [16, 61, 9, 10, 28],
 18: [8, 58, 90, 13, 48],
 6: [20, 25, 94, 84, 5],
 17: [56, 52, 47, 59, 96],
 1: [73, 32, 67, 91, 1],
 14: [11, 2, 35, 46, 98],
 9: [37, 17, 76, 12, 68],
 13: [77, 26, 45, 99, 79],
 16: [65, 50, 74, 36, 80]}
def create_flders(splits,args):
    Flags = {}
    Flags['Dir']='task_net_models/'
    Flags['MNT']=args.out_path+'/'
    Flags['sPath']=Flags['MNT']+args.environment+'/'
    Dir_Use=splits
    savedModels=['imScores','savedModels']


    #remove existing directory
    if os.path.exists(Flags['sPath']) and os.path.isdir(Flags['sPath']):
        shutil.rmtree(Flags['sPath'])
    
    #create the directory
    os.makedirs(Flags['sPath'])
    for directory in Dir_Use:
        if not os.path.exists(Flags['sPath']+str(int(directory*100))):
            os.makedirs(Flags['sPath']+str(int(directory*100)))
            Flags[str(int(directory*100))]=Flags['sPath']+str(int(directory*100))+'/'


    # if not os.path.exists(Flags['sPath']):
    #     os.makedirs(Flags['sPath']+environment)
    return Flags

def config_to_str(config):
    attrs = vars(config)
    string_val = "Config: -----\n"
    string_val += "\n".join("%s: %s" % item for item in attrs.items())
    string_val += "\n----------"
    return string_val

def cifar_transformer():
    return transforms.Compose([
            transforms.ToTensor(),
                # transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
            # transforms.Normalize(mean=[0.5, 0.5, 0.5,],
            #                     std=[0.5, 0.5, 0.5]),
        ])
def caltech_transformer():
    return transforms.Compose([
         transforms.Resize(size=256),
        transforms.CenterCrop(size=224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        # transforms.Scale(256),
        # transforms.CenterCrop(224),
        # transforms.ToTensor(),
        #   transforms.Normalize(mean=[0.485, 0.456, 0.406],
        #                         std=[0.229, 0.224, 0.225])
            # transforms.RandomResizedCrop(224),
            # transforms.ToTensor(),
                # transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
            # transforms.Normalize(mean=[0.5, 0.5, 0.5,],
            #                     std=[0.5, 0.5, 0.5]),
        ])

def plot_visdom(vis,x,y,winName,plotName):
    options = dict(fillarea=False,width=400,height=400,xlabel='Iteration',ylabel='Loss',title=winName)
    if (vis.win_exists(winName)==False):
        win = vis.line(X=np.array([0]),Y=np.array([0]),win=winName,name=plotName,opts=options)
    else:
        vis.line(X=np.array([x]),Y=np.array([y]),win=winName,update='append',name=plotName)

        
def main(args):

    # import the correct loss and training functions depending which model to optimize
    # TODO: these could easily be refactored into one function, but we kept it this way for modularity
    
    environment=args.environment+ '_'+str(args.percentage_corruped*100)
    cfg = {"server": "jmandivarapu1@retina.cs.gsu.edu","port": 8097}
    vis = visdom.Visdom('http://' + cfg["server"], port = cfg["port"])
    vis.delete_env(args.environment+ '_'+str(args.percentage_corruped*100)) #If you want to clear all the old plots for this python Experiments.Resets the Environment
    vis = visdom.Visdom('http://' + cfg["server"], port = cfg["port"],env=environment)

    # vis = visdom.Visdom()
    
    # vis.delete_env(environment) #If you want to clear all the old plots for this python Experiments.Resets the Environment
    # vis = visdom.Visdom(env=environment)
    if args.train_var:
        if args.joint:
            print("came to the Joint Training")
            from lib.Training.train import train_var_joint as train
            from lib.Training.validate import validate_var_joint as validate
            from lib.Training.loss_functions import var_loss_function_joint as criterion
        else:
            print("came to the expected loop")
            from lib.Training.train import train_var as train
            from lib.Training.validate import validate_var as validate
            from lib.Training.loss_functions import var_loss_function as criterion
        from lib.Training.evaluate import eval_var_dataset as evaluate
    else:
        if args.joint:
            from lib.Training.train import train_joint as train
            from lib.Training.validate import validate_joint as validate
            from lib.Training.loss_functions import loss_function_joint as criterion
        else:
            from lib.Training.train import train as train
            from lib.Training.validate import validate as validate
            from lib.Training.loss_functions import loss_function as criterion
    from lib.OpenSet.meta_recognition import Weibull_Sampler as WieBullSampler



    if args.dataset == 'cifar10':
        test_dataloader = data.DataLoader(
                datasets.CIFAR10(args.data_path, download=True, transform=cifar_transformer(), train=False),
            batch_size=args.batch_size, drop_last=False)
        
        train_dataset = CIFAR10(args.data_path)
        args.num_images = 50000
        args.num_val = 5000
        args.budget = 2500
        args.initial_budget = 5000
        args.num_classes = 10
    elif args.dataset == 'cifar100':
        test_dataloader = data.DataLoader(
                datasets.CIFAR100(args.data_path, download=True, transform=cifar_transformer(), train=False),
             batch_size=args.batch_size, drop_last=False)

        train_dataset = CIFAR100(args.data_path)
        print("=========CIFAR 100===============")
        args.num_val = 5000
        args.num_images = 50000
        args.budget = 2500
        args.initial_budget = 5000
        args.num_classes = 100

    elif args.dataset == 'imagenet':
        test_dataloader = data.DataLoader(
                datasets.ImageFolder(args.data_path, transform=imagenet_transformer()),
            drop_last=False, batch_size=args.batch_size)

        train_dataset = ImageNet(args.data_path)

        args.num_val = 128120
        args.num_images = 1281167
        args.budget = 64060
        args.initial_budget = 128120
        args.num_classes = 1000
    elif args.dataset == 'caltech256':
        print("path os fata is",args.data_path)
        test_dataloader = data.DataLoader(datasets.ImageFolder(args.data_path+'test/',transform=caltech_transformer()),drop_last=True, batch_size=args.test_batch_size)
        train_dataset = Caltech256(args.data_path+'train/')
        print(len(train_dataset),len(test_dataloader))

        # args.num_val = 00
        # args.num_images = 6500
        # args.budget = 1530
        # args.initial_budget = 6000
        # args.num_classes = 256
        args.num_val = 2700
        args.num_images = 26683
        args.budget = 1530
        args.initial_budget = 3060
        args.num_classes = 256
    elif args.dataset == 'Cityscapes':
        test_dataloader = data.DataLoader(
                datasets.Cityscapes(args.data_path,download=True, transform=imagenet_transformer()),
            drop_last=False, batch_size=args.batch_size)

        train_dataset = Cityscapes(args.data_path)

        args.num_val = 128120
        args.num_images = 1281167
        args.budget = 64060
        args.initial_budget = 128120
        args.num_classes = 1000
    else:
        raise NotImplementedError
    
    if args.sameIndexs:
        print("Setting the random Index")
        random.seed(30)
    args.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Config: %s" % config_to_str(args))
    all_indices = set(np.arange(args.num_images))
    val_indices = random.sample(all_indices, args.num_val)
    all_indices = np.setdiff1d(list(all_indices), val_indices)
    initial_indices = random.sample(list(all_indices), args.initial_budget)
    sampler = data.sampler.SubsetRandomSampler(initial_indices)
    val_sampler = data.sampler.SubsetRandomSampler(val_indices)

    #The below lines are only for weibull distrubution which need two validation sets to pll off
    val_indices_set1=val_indices[0:int(len(val_indices)/2)]
    val_indices_set2=val_indices[int(len(val_indices)/2):]
    val_sampler_set1 = data.sampler.SubsetRandomSampler(val_indices_set1)
    val_sampler_set2 = data.sampler.SubsetRandomSampler(val_indices_set2)
    val_dataloader_set1 = data.DataLoader(train_dataset, sampler=val_sampler_set1,batch_size=args.batch_size, drop_last=False)
    val_dataloader_set2 = data.DataLoader(train_dataset, sampler=val_sampler_set2,batch_size=args.batch_size, drop_last=False)

    # dataset with labels available
    querry_dataloader = data.DataLoader(train_dataset, sampler=sampler, batch_size=args.batch_size, drop_last=False)
    val_dataloader = data.DataLoader(train_dataset, sampler=val_sampler,batch_size=args.batch_size, drop_last=False)

    print("length of the Querry loader",len(querry_dataloader)*args.batch_size)
    print("length of the Test loader",len(test_dataloader)*args.batch_size)
    print("length of the Validation loader",len(val_dataloader)*args.batch_size)
    print("length of the Validation loader ",len(val_dataloader_set1)*args.batch_size) 
    print("length of the Validation loader",len(val_dataloader_set2)*args.batch_size)  
    args.cuda = torch.cuda.is_available()

    solver = Solver(args, test_dataloader,val_dataloader_set1,val_dataloader_set2)

    splits = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4]

    current_indices = list(initial_indices)

    accuracies = []

    Flags=create_flders(splits,args)
    print(Flags)
    
    acc_options = dict(fillarea=True,width=400,height=400,xlabel='Percentage of Corrupted',ylabel='Total',title=str('corrupt percentage'))
    

    for split in splits:
        num_colors=3
        iterations=0
        epoch = 0
        best_prec = 0
        best_acc=0
        best_loss = random.getrandbits(128)
        lr_change=[150,250]
       
        #task_model=model.WRN(args.device,args.num_classes, num_colors, args)
        if args.dataset == 'caltech256':
            task_model=model.WRN_caltech_actual(args.device,args.num_classes, num_colors, args)#models.vgg16(pretrained=True)#
            # for param in task_model.parameters():
            #     param.requires_grad = False
            #     # n_inputs = 25088#task_model.classifier[6].in_features
            #     # Add on classifier
            #     task_model.classifier[6] = nn.Sequential(
            #         nn.Linear(4096, 256), nn.ReLU(), nn.Dropout(0.2),
            #         nn.Linear(256, 256), nn.LogSoftmax(dim=1))
        else:
            task_model=model.WRN_actual(args.device,args.num_classes, num_colors, args)
        #print("mode",task_model)
        
        task_model.train()
        # task_model.load_state_dict(torch.load('save_path/best_0.pt'))
        if args.cuda:
            task_model = task_model.cuda()
            #task_model = torch.nn.DataParallel(task_model).to(args.device)
        #summary(task_model, (3, 32, 32))
        # WeightInitializer = WeightInit(args.weight_init)
        # WeightInitializer.init_model(task_model)
        unlabeled_indices = np.setdiff1d(list(all_indices), current_indices)
        unlabeled_sampler = data.sampler.SubsetRandomSampler(unlabeled_indices)
        unlabeled_dataloader = data.DataLoader(train_dataset, 
                sampler=unlabeled_sampler, batch_size=args.batch_size, drop_last=False)
        
        print("length od the Unlabled loader",len(unlabeled_dataloader)*128)  
        '''
        The below few lines until the while loop
        it will modify percentage of labels from the existing to the coarse label in the
        same super class. The percentage will be specified in the YAML file arguments
        1.Copy the orginal indexes before the loop starts
        2. Sample 10% of current indexes and change it's targets
        '''
        #This will keep copy of targets of intial poo;
        orginal_targets=list(querry_dataloader.dataset.cifar100.targets)
        sampled_indexes=random.sample(current_indices, int(args.percentage_corruped*len(current_indices)))
        print("len of samplerindexe",len(sampled_indexes))
        for selected_index in sampled_indexes:
            selected_index_current_label=querry_dataloader.dataset.cifar100.targets[selected_index] 
            for i in range(0,20):
                if selected_index_current_label in d[i]:
                    copy=list(d[i])
                    index=copy.index(selected_index_current_label)
                    del copy[index]
                    new_target=random.choice(copy)
                    querry_dataloader.dataset.cifar100.targets[selected_index] = new_target
                    i=21
                    print('{} selected_index is {} and current label is{}, {}, new label is {}'.format(copy,selected_index,orginal_targets[selected_index],selected_index_current_label,querry_dataloader.dataset.cifar100.targets[selected_index]))
        # copy_indexs=querry_dataloader.dataset.cifar100.targets
        # with open('queeryloader', 'wb') as fp:pickle.dump(querry_dataloader.dataset.cifar100.targets, fp)
        # with open('orginialindexe', 'wb') as fp:pickle.dump(orginal_targets, fp)
        ccount=0
        for i in range(0,len(orginal_targets)):
            if orginal_targets[i]!=querry_dataloader.dataset.cifar100.targets[i]:
                ccount=ccount+1
        vis.bar(X=[ccount,0],win='ACC'+str(int(split*100)),opts=acc_options)
        print("Percentage of difference between the labels from the orginal and corrupted is",ccount,ccount/len(current_indices))
        #args.percentage_corruped labels has been changed until now
        optimizer = torch.optim.Adam(task_model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
        while epoch < args.epochs:
            if (epoch in lr_change):
                for param in optimizer.param_groups:
                    param['lr'] = param['lr'] / 10
            # train
            finished_iter,acc,loss=train(querry_dataloader,
                    validate,
                    test_dataloader,
                    task_model, 
                    criterion, 
                    epoch, 
                    optimizer,
                    vis, 
                    args.device, 
                    args,
                    split,
                    iterations)
        
            # evaluate on validation set
            # acc, loss = validate(, task_model, criterion, epoch, vis, args.device, args)
            iterations=finished_iter
            
            # increment epoch counters
            epoch += 1
           
                    # remember best prec@1 and save checkpoint
            is_best = best_acc < acc
            if is_best:
                best_acc=acc
                save_path=Flags[str(int(split*100))]
                best_model=task_model
                torch.save(task_model.state_dict(),os.path.join(Flags[str(int(split*100))],"best_"+str(int(best_acc))+".pt"))
                save_checkpoint({'epoch': epoch,
                                'state_dict': task_model.state_dict(),
                                'best_prec': best_prec,
                                'best_loss': best_loss,
                                'optimizer': optimizer.state_dict()},
                                is_best, save_path)
        accuracies.append(best_acc)
        print("All accuracies until now",accuracies)
        GPUs = GPU.getGPUs()
        for gpu in GPUs:print("GPU RAM Free: {0:.0f}MB | Used: {1:.0f}MB | Util {2:3.0f}% | Total {3:.0f}MB".format(gpu.memoryFree, gpu.memoryUsed, gpu.memoryUtil*100, gpu.memoryTotal))
        with open(save_path+'acc_'+str(int(len(accuracies))), 'wb') as fp:pickle.dump(accuracies, fp)
        print('Final accuracy with {}% of data is: {:.2f}'.format(int(split*100), acc))
        sampled_indices=WieBullSampler(best_model,querry_dataloader,test_dataloader,val_dataloader,unlabeled_dataloader,val_dataloader_set1,val_dataloader_set2,evaluate,args,save_path)
        current_indices = list(current_indices) + list(sampled_indices)
        #Now before going to the sampler again we need to replace our old targets back again
        querry_dataloader.dataset.cifar100.targets=list(orginal_targets) #Reset back to orginal
        sampler = data.sampler.SubsetRandomSampler(current_indices)
        querry_dataloader = data.DataLoader(train_dataset, sampler=sampler, 
                batch_size=args.batch_size, drop_last=True)
        
    torch.save(accuracies, os.path.join(args.out_path, args.log_name))

if __name__ == '__main__':
    args = arguments_yaml.get_args()
    with open(args.work_path) as f:
        config = yaml.load(f)
    # convert to dict
    args = EasyDict(config)
    main(args)

